import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type Tone = "info" | "success" | "warning" | "danger";

const TONES: Record<Tone, { box: string; icon: string; path: string }> = {
  info: {
    box: "bg-info-soft text-fg border-info/30",
    icon: "text-info",
    path: "M8 1a7 7 0 100 14A7 7 0 008 1zm0 3a1 1 0 110 2 1 1 0 010-2zm.75 4.25v3.5a.75.75 0 01-1.5 0v-3.5a.75.75 0 011.5 0z",
  },
  success: {
    box: "bg-ok-soft text-fg border-ok/30",
    icon: "text-ok",
    path: "M8 1a7 7 0 100 14A7 7 0 008 1zm3.03 5.03l-3.5 3.5a.75.75 0 01-1.06 0l-1.5-1.5a.75.75 0 111.06-1.06L7 7.94l2.97-2.97a.75.75 0 111.06 1.06z",
  },
  warning: {
    box: "bg-warn-soft text-fg border-warn/30",
    icon: "text-warn",
    path: "M7.1 2.5a1 1 0 011.8 0l5 9.5A1 1 0 0113 13.5H3a1 1 0 01-.9-1.5l5-9.5zM8 6a.75.75 0 00-.75.75v2.5a.75.75 0 001.5 0v-2.5A.75.75 0 008 6zm0 5a1 1 0 110 2 1 1 0 010-2z",
  },
  danger: {
    box: "bg-bad-soft text-fg border-bad/30",
    icon: "text-bad",
    path: "M8 1a7 7 0 100 14A7 7 0 008 1zm0 3.5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 018 4.5zM8 11a1 1 0 110 2 1 1 0 010-2z",
  },
};

export type AlertProps = {
  tone?: Tone;
  title?: string;
  children?: ReactNode;
  className?: string;
  /**
   * Shows a dismiss button when given.
   *
   * Only for notices that report something that already happened — "the role was deleted".
   * A validation error has no dismiss button on purpose: the way to make it go away is to
   * fix the field, and a close button invites people to clear the message and resubmit the
   * same thing.
   */
  onDismiss?: () => void;
};

/**
 * `role="alert"` on anything that reports a failure, so a screen reader announces it as
 * soon as it renders. Informational notes use `role="status"`, which is polite and waits
 * for a pause rather than interrupting.
 */
export function Alert({ tone = "info", title, children, className, onDismiss }: AlertProps) {
  const style = TONES[tone];
  const assertive = tone === "danger" || tone === "warning";

  return (
    <div
      role={assertive ? "alert" : "status"}
      className={cn("animate-fade flex gap-3 rounded-lg border p-3 text-sm", style.box, className)}
    >
      <svg
        viewBox="0 0 16 16"
        className={cn("mt-0.5 size-4 shrink-0", style.icon)}
        fill="currentColor"
        aria-hidden
      >
        <path d={style.path} />
      </svg>
      <div className="min-w-0 flex-1 space-y-0.5">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className="text-fg-2 [&_p]:leading-relaxed">{children}</div>}
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="-m-1 shrink-0 self-start rounded-md p-1 text-fg-3 transition-colors hover:text-fg"
        >
          <svg
            viewBox="0 0 16 16"
            className="size-3.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            aria-hidden
          >
            <path d="M4 4l8 8M12 4l-8 8" />
          </svg>
        </button>
      )}
    </div>
  );
}
