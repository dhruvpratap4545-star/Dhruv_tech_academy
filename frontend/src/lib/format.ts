/**
 * Display formatting. Indian conventions throughout: DD-MM-YYYY dates and the Indian
 * digit grouping for currency (1,00,000 — not 100,000), which `en-IN` gives us for free.
 */

const DATE = new Intl.DateTimeFormat("en-IN", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

const DATE_TIME = new Intl.DateTimeFormat("en-IN", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: true,
});

const RUPEES = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

function parse(value: string | Date | null | undefined): Date | null {
  if (!value) return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** DD-MM-YYYY. Intl gives DD/MM/YYYY for en-IN, so the separator is swapped. */
export function formatDate(value: string | Date | null | undefined, fallback = "—"): string {
  const date = parse(value);
  return date ? DATE.format(date).replace(/\//g, "-") : fallback;
}

export function formatDateTime(value: string | Date | null | undefined, fallback = "—"): string {
  const date = parse(value);
  return date ? DATE_TIME.format(date).replace(/\//g, "-") : fallback;
}

export function formatRupees(paise: number | null | undefined, fallback = "—"): string {
  return typeof paise === "number" ? RUPEES.format(paise) : fallback;
}

/**
 * "2 hours ago" for recent activity, falling back to a date once it stops being useful.
 * Relative time is friendlier at a glance; an exact date matters more after a few days.
 */
export function formatRelative(value: string | Date | null | undefined): string {
  const date = parse(value);
  if (!date) return "Never";

  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return "Just now";

  const relative = new Intl.RelativeTimeFormat("en-IN", { numeric: "auto" });
  const steps: [Intl.RelativeTimeFormatUnit, number][] = [
    ["minute", 60],
    ["hour", 3600],
    ["day", 86400],
  ];
  for (const [unit, size] of steps) {
    if (seconds < size * (unit === "day" ? 7 : 60)) {
      return relative.format(-Math.round(seconds / size), unit);
    }
  }
  return formatDate(date);
}

/** Initials for an avatar. Two letters at most, so the circle never overflows. */
export function initials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase();
}

/** "branch_admin" -> "Branch Admin", for any key the API has no display name for. */
export function humanise(key: string): string {
  return key
    .split(/[_:]/)
    .filter(Boolean)
    .map((word) => word[0]!.toUpperCase() + word.slice(1))
    .join(" ");
}
