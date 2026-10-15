import type { ReactNode } from "react";
import { useEffect, useId, useRef } from "react";

import { cn } from "@/lib/cn";

export type ModalProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg";
};

const SIZES = { sm: "max-w-md", md: "max-w-lg", lg: "max-w-2xl" } as const;

/**
 * Dialog built on the native `<dialog>` element.
 *
 * Using the platform element rather than a div means focus trapping, the top layer, inert
 * background content and Escape-to-close are the browser's job, not three hundred lines of
 * ours — and they behave correctly with screen readers for free.
 */
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md",
}: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    // Fires for Escape as well as dialog.close(), so one handler covers both.
    const handleClose = () => onClose();
    dialog.addEventListener("close", handleClose);
    return () => dialog.removeEventListener("close", handleClose);
  }, [onClose]);

  const baseId = useId();

  return (
    <dialog
      ref={ref}
      // Generated, not hardcoded. Four dialogs can be mounted at once on the users
      // screen, and a fixed id gave all four the same one — so `aria-labelledby` could
      // resolve to another dialog's heading and announce the wrong title.
      aria-labelledby={`${baseId}-title`}
      aria-describedby={description ? `${baseId}-description` : undefined}
      // The backdrop is styled through ::backdrop in index.css rather than an extra div.
      className={cn(
        "m-auto w-[calc(100vw-2rem)] rounded-xl border border-line bg-surface p-0",
        "text-fg shadow-overlay backdrop:bg-black/50 backdrop:backdrop-blur-sm",
        "open:animate-in",
        SIZES[size],
      )}
      onClick={(event) => {
        // Clicking the backdrop closes. The dialog element itself fills only the panel,
        // so a click landing directly on it means the backdrop was hit.
        if (event.target === ref.current) onClose();
      }}
    >
      <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
        <div className="min-w-0 space-y-1">
          <h2 id={`${baseId}-title`} className="text-base font-semibold">
            {title}
          </h2>
          {description && (
            <p id={`${baseId}-description`} className="text-sm text-fg-2">
              {description}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="-m-1 rounded-md p-1 text-fg-3 transition-colors hover:bg-surface-2 hover:text-fg"
        >
          <svg viewBox="0 0 16 16" className="size-5" fill="none" aria-hidden>
            <path
              d="M4 4l8 8M12 4l-8 8"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </div>

      <div className="max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div>

      {footer && (
        <div className="flex flex-wrap justify-end gap-2 border-t border-line bg-bg px-5 py-3">
          {footer}
        </div>
      )}
    </dialog>
  );
}
