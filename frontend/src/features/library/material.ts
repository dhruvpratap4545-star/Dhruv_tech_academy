/** Pure helpers for showing material safely. No React, so they are unit-tested directly. */

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

/** Where a stored file is downloaded. The API checks access and redirects to a signed link. */
export function fileUrl(fileId: string): string {
  return `${API_BASE}/files/${encodeURIComponent(fileId)}`;
}

/**
 * The embed address for a stored video id, or null for anything unexpected.
 *
 * Built from the id the server already validated and normalised, never from the URL a
 * person pasted, and checked again here against the id shapes each provider uses — so an
 * attacker-controlled string can never become an iframe source.
 */
export function embedUrl(provider: string | null, videoId: string | null): string | null {
  if (!provider || !videoId) return null;
  if (provider === "youtube" && /^[A-Za-z0-9_-]{11}$/.test(videoId)) {
    return `https://www.youtube-nocookie.com/embed/${videoId}`;
  }
  if (provider === "vimeo" && /^\d{4,12}$/.test(videoId)) {
    return `https://player.vimeo.com/video/${videoId}`;
  }
  return null;
}

/** Only https links are shown as links; anything else is shown as text. */
export function safeHref(url: string | null): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" ? parsed.toString() : null;
  } catch {
    return null;
  }
}

/** The form's own checks, before anything is sent. Returns a message key or null. */
export function validateMaterial(input: {
  kind: string;
  title: string;
  nodeIds: string[];
  url: string;
  body: string;
  files: File[];
}):
  | "library.error.title"
  | "library.error.topics"
  | "library.error.file"
  | "library.error.url"
  | "library.error.body"
  | null {
  if (input.title.trim().length < 2) return "library.error.title";
  if (input.nodeIds.length === 0) return "library.error.topics";
  if ((input.kind === "pdf" || input.kind === "image") && input.files.length !== 1)
    return "library.error.file";
  if ((input.kind === "link" || input.kind === "video_link") && !safeHref(input.url.trim()))
    return "library.error.url";
  if (input.kind === "text" && !input.body.trim()) return "library.error.body";
  return null;
}
