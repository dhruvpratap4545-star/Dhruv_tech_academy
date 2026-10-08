import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type Tone = "neutral" | "primary" | "success" | "warning" | "danger" | "accent";

const TONES: Record<Tone, string> = {
  neutral: "bg-surface-3 text-fg-2",
  primary: "bg-accent-soft text-accent-ink",
  success: "bg-ok-soft text-ok",
  warning: "bg-warn-soft text-warn",
  danger: "bg-bad-soft text-bad",
  accent: "bg-accent-subtle text-accent",
};

export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Status pill with a fixed colour per state, so it reads the same on every screen. */
export function StatusBadge({ status }: { status: string }) {
  const tone: Tone =
    status === "active"
      ? "success"
      : status === "invited"
        ? "warning"
        : status === "suspended"
          ? "danger"
          : "neutral";
  const label = status.charAt(0).toUpperCase() + status.slice(1);
  return <Badge tone={tone}>{label}</Badge>;
}
