import { cn } from "@/lib/cn";

/**
 * The client's own crest, from `legacy/static/images/logo.png`.
 *
 * Served as `logo-128.png` rather than the 222 KB original: that file is 500x500 and would
 * be downloaded in full on every page just to be drawn at 32px. The derivatives are
 * generated once from the same source, so the brand has one origin and the web build is
 * 32 KB rather than a fifth of a megabyte.
 *
 * 128px covers every size this appears at, including 40px on a 3x phone screen.
 *
 * One honest limitation: the crest carries fine ring text ("PREMIUM ONLINE DIGITAL
 * EDUCATION"). Below roughly 48px that text stops being legible and what remains is the
 * silhouette — gold ring, navy mortarboard. That is inherent to an ornate crest, and the
 * fix is not to redraw the client's logo. Wherever it appears small it sits beside the
 * "Dhruv Academy" wordmark, which does the naming.
 */
export function Logo({ className }: { className?: string }) {
  return (
    <img
      src="/logo-128.png"
      alt="Dhruv Academy"
      width={128}
      height={128}
      // Above the fold on every page, so never deferred — a late logo is a visible flinch.
      loading="eager"
      decoding="async"
      className={cn("size-8 shrink-0 object-contain", className)}
    />
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <Logo />
      {/* Hidden on the narrowest screens: at 360px the text wraps and squeezes the rest
          of the header. The mark alone still identifies the app. */}
      <span className="hidden font-display text-base font-extrabold tracking-tight whitespace-nowrap text-fg xs:inline">
        Dhruv Academy
      </span>
    </span>
  );
}

/** Initials avatar, used in the header and in every user row. */
export function Avatar({
  initials,
  className,
  tone = "accent",
}: {
  initials: string;
  className?: string;
  tone?: "accent" | "brand";
}) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-flex size-8 shrink-0 items-center justify-center rounded-full text-[11px] font-bold",
        tone === "accent" ? "bg-accent-soft text-accent-ink" : "bg-brand text-brand-fg",
        className,
      )}
    >
      {initials}
    </span>
  );
}
