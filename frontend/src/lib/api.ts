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
}

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  /** Internal: stops a refreshed request from recursing. */
  retry?: boolean;
};

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
  inFlightRefresh ??= fetch(`${BASE_URL}/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  })
    .then((response) => response.ok)
    .catch(() => false)
    .finally(() => {
      inFlightRefresh = null;
    });
  return inFlightRefresh;
}

/** Called by the auth layer on logout, so a stale attempt cannot revive a dead session. */
export function cancelPendingRefresh(): void {
  inFlightRefresh = null;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal, retry = true } = options;

  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    signal,
    credentials: "include",
    headers: {
      "X-Requested-With": "XMLHttpRequest",
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  // An expired access token is the normal case every 15 minutes: rotate once and replay.
  if (response.status === 401 && retry && !path.startsWith("/auth/")) {
    if (await refreshSession()) {
      return apiFetch<T>(path, { ...options, retry: false });
    }
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
