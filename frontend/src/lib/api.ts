/**
 * The only place the frontend talks to the API.
 *
 * Auth travels in httpOnly cookies, so every request sends credentials and the CSRF header
 * the backend requires on state-changing methods (PRD §7.5). This module never reads,
 * writes or even sees a token.
 */

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

/** Error shape the API always returns: `{"error": {"code", "message"}}` (PRD §8). */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** True when the server rejected the input rather than the caller. */
  get isValidation(): boolean {
    return this.status === 422;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  /** The request never reached the server. Status 0 because there was no response. */
  get isOffline(): boolean {
    return this.status === 0;
  }
}

/**
 * Turn a dead network into a sentence a person can act on.
 *
 * `fetch` rejects with a bare `TypeError: Failed to fetch` for everything from a dropped
 * connection to a DNS failure to a CORS refusal. Letting that reach the screen produces
 * "Failed to fetch" on a banner, which tells somebody on a train precisely nothing. The
 * app does not block anything while offline — it lets the request go and says this when it
 * comes back empty-handed.
 */
function networkError(cause: unknown): ApiError {
  if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
  const offline = typeof navigator !== "undefined" && navigator.onLine === false;
  return new ApiError(
    0,
    "OFFLINE",
    offline
      ? "You are offline, so that could not be saved. Reconnect and try again — nothing has been lost."
      : "We could not reach the server. Check your connection and try again.",
  );
}

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  /**
   * JSON by default. A `FormData` body is sent as it is, with no `Content-Type` header:
   * the browser has to write that one itself, because only it knows the multipart
   * boundary it generated. Setting it by hand produces a body the server cannot parse.
   */
  body?: unknown;
  signal?: AbortSignal;
  /** Internal: stops a refreshed request from recursing. */
  retry?: boolean;
};

function isFormData(body: unknown): body is FormData {
  return typeof FormData !== "undefined" && body instanceof FormData;
}

/**
 * One refresh in flight at a time.
 *
 * A dashboard fires several queries at once, so an expired access token produces a burst
 * of 401s. Without this they would each POST /auth/refresh, and because refresh tokens
 * rotate, the second one would present an already-used token — which the backend correctly
 * treats as theft and responds to by killing the whole session family. Sharing one promise
 * turns that burst into a single rotation.
 */
let inFlightRefresh: Promise<boolean> | null = null;

function refreshSession(): Promise<boolean> {
  if (inFlightRefresh) return inFlightRefresh;

  const attempt = fetch(`${BASE_URL}/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  })
    .then((response) => response.ok)
    .catch(() => false);

  inFlightRefresh = attempt;

  // Clear the slot only if it still holds *this* attempt. An unconditional reset lets a
  // cancelled-then-restarted refresh null out its successor's slot when it finally
  // settles, after which a third caller starts a second rotation alongside the first —
  // and two refresh tokens in flight is exactly what the backend treats as theft,
  // answering by killing the whole session family.
  void attempt.finally(() => {
    if (inFlightRefresh === attempt) inFlightRefresh = null;
  });

  return attempt;
}

/** Called by the auth layer on logout, so a stale attempt cannot revive a dead session. */
export function cancelPendingRefresh(): void {
  inFlightRefresh = null;
}

let sessionExpired: (() => void) | null = null;

/**
 * Register what to do when the session is definitively gone — a 401 that survived a
 * refresh attempt.
 *
 * Without this the app has no idea it has been signed out. Every request just fails,
 * the screen keeps showing stale data, and the person sits on a page where nothing
 * works and nothing explains why. The auth layer registers a handler that drops the
 * cached user, which lets the route guards send them to the login page.
 *
 * A callback rather than importing the query client here: the HTTP layer should not
 * depend on the cache, and the cache module already imports this one.
 */
export function onSessionExpired(handler: () => void): void {
  sessionExpired = handler;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal, retry = true } = options;

  const multipart = isFormData(body);
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      signal,
      credentials: "include",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        ...(body === undefined || multipart ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : multipart ? body : JSON.stringify(body),
    });
  } catch (cause) {
    throw networkError(cause);
  }

  // An expired access token is the normal case every 15 minutes: rotate once and replay.
  if (response.status === 401 && retry && !path.startsWith("/auth/")) {
    if (await refreshSession()) {
      return apiFetch<T>(path, { ...options, retry: false });
    }
    // The refresh failed too, so this session is over — signed out elsewhere, revoked,
    // or simply expired. Tell the auth layer rather than letting the caller swallow a
    // 401 and leave a dead screen on display.
    sessionExpired?.();
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const error = (payload as { error?: { code?: string; message?: string } } | null)?.error;
    throw new ApiError(
      response.status,
      error?.code ?? "UNKNOWN",
      error?.message ?? "Something went wrong. Please try again.",
    );
  }

  return payload as T;
}

/** Envelope every list endpoint returns (PRD §8). */
export type Page<T> = {
  items: T[];
  next_cursor: string | null;
  /**
   * How many rows match the current filters across every page.
   *
   * Cursor paging produces no total of its own — that is the trade for its speed, and it
   * is why "Next" is the only control such a list can honestly offer. The server counts
   * separately so a screen can say "Page 3 of 7" and "Showing 41–60 of 134", which is what
   * people actually want from a list: a sense of how much there is.
   */
  total: number;
};

/** Build a query string, dropping empty values so the URL stays readable. */
export function query(params: Record<string, string | number | boolean | null | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

/**
 * Fetch a file the API generates, and hand the browser a download.
 *
 * Not `apiFetch`: the response is a workbook, not JSON, and it has to travel with the
 * session cookie — which a plain `<a href>` to the API would also do, but then a 403 would
 * render as a bare error page in a new tab rather than as a message on the screen the
 * person is looking at.
 */
export async function apiDownload(path: string, filename: string): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      credentials: "include",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
  } catch (cause) {
    throw networkError(cause);
  }

  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const error = (payload as { error?: { code?: string; message?: string } } | null)?.error;
    throw new ApiError(
      response.status,
      error?.code ?? "UNKNOWN",
      error?.message ?? "That file could not be downloaded.",
    );
  }

  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  // Released on the next tick: revoking it synchronously races the click in Safari and
  // the file arrives empty.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
