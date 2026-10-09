import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { useId, useState } from "react";

import { cn } from "@/lib/cn";

const CONTROL = [
  "w-full rounded-lg border bg-surface px-3 text-sm text-fg",
  "placeholder:text-fg-3",
  "transition-[border-color,box-shadow] duration-(--duration-fast)",
  "disabled:cursor-not-allowed disabled:bg-bg disabled:opacity-70",
].join(" ");

type FieldShellProps = {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  /**
   * A control that belongs beside the label rather than under the field — "Forgot
   * password?" next to Password being the case this exists for. Below the input it reads
   * as detached from the field and is easy to miss at exactly the moment it is needed.
   */
  action?: ReactNode;
  children: (ids: { controlId: string; describedBy: string | undefined }) => ReactNode;
};

/**
 * Label, control, hint and error as one unit.
 *
 * The wiring here is the point: the label is bound to the control by id, and the hint and
 * error are announced through `aria-describedby`. A visually obvious error that a screen
 * reader never mentions is not an error message.
 */
export function Field({ label, hint, error, required, action, children }: FieldShellProps) {
  const controlId = useId();
  const hintId = `${controlId}-hint`;
  const errorId = `${controlId}-error`;
  const describedBy =
    [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;

  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={controlId} className="block text-sm font-medium text-fg">
          {label}
          {required && (
            <span className="ml-0.5 text-bad" aria-hidden="true">
              *
            </span>
          )}
        </label>
        {action}
      </div>

      {children({ controlId, describedBy })}

      {hint && !error && (
        <p id={hintId} className="text-xs text-fg-2">
          {hint}
        </p>
      )}
      {error && (
        /* `role="alert"` so the message is read the moment it appears, not only when
           the user happens to move focus back to the field. */
        <p id={errorId} role="alert" className="flex items-center gap-1 text-xs text-bad">
          <svg viewBox="0 0 16 16" className="size-3.5 shrink-0" fill="currentColor" aria-hidden>
            <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 3.5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 018 4.5zM8 11a1 1 0 110 2 1 1 0 010-2z" />
          </svg>
          {error}
        </p>
      )}
    </div>
  );
}

function controlClasses(hasError: boolean, extra?: string) {
  return cn(
    CONTROL,
    hasError
      ? "border-bad focus:border-bad"
      : "border-line hover:border-line-strong focus:border-accent",
    extra,
  );
}

export type TextFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "id"> & {
  label: string;
  hint?: string;
  error?: string;
  action?: ReactNode;
};

export function TextField({ label, hint, error, action, className, ...rest }: TextFieldProps) {
  // `type="password"` gets a reveal button, always. Typing a password blind is where
  // sign-in failures come from that have nothing to do with the password being wrong —
  // a capital letter held a moment too long, a phone keyboard that autocorrected, a
  // character that is simply not where the person thought it was. The browser offers no
  // such control of its own on most platforms, so the form has to.
  const isPassword = rest.type === "password";
  const [revealed, setRevealed] = useState(false);

  return (
    <Field label={label} hint={hint} error={error} required={rest.required} action={action}>
      {({ controlId, describedBy }) => (
        <div className={isPassword ? "relative" : undefined}>
          <input
            id={controlId}
            aria-describedby={describedBy}
            aria-invalid={error ? true : undefined}
            className={controlClasses(Boolean(error), cn("h-11", isPassword && "pr-11", className))}
            {...rest}
            type={isPassword && revealed ? "text" : rest.type}
          />
          {isPassword && (
            <button
              type="button"
              // A normal tab stop. It was taken out of the tab order to keep the path
              // from the field to the submit button short, which made the control
              // unreachable for anybody without a pointer — a WCAG 2.1.1 failure, and the
              // people most likely to need to check what they typed are exactly the ones
              // it locked out. Every browser and password manager puts a stop here too.
              onClick={() => setRevealed((shown) => !shown)}
              aria-label={revealed ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
              aria-pressed={revealed}
              className={cn(
                "absolute top-1/2 right-1 flex size-9 -translate-y-1/2 items-center justify-center",
                "rounded-md text-fg-3 transition-colors hover:bg-surface-2 hover:text-fg",
                // It is in the tab order now, so it has to show where focus is.
                "focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none",
              )}
            >
              <EyeIcon off={revealed} />
            </button>
          )}
        </div>
      )}
    </Field>
  );
}

/** An eye, struck through once the password is on screen. */
function EyeIcon({ off }: { off: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className="size-4.5"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z" />
      <circle cx="12" cy="12" r="2.6" />
      {off && <path d="M4 20 20 4" />}
    </svg>
  );
}

export type SelectFieldProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, "id"> & {
  label: string;
  hint?: string;
  error?: string;
  placeholder?: string;
  options: { value: string; label: string; disabled?: boolean }[];
};

export function SelectField({
  label,
  hint,
  error,
  placeholder,
  options,
  className,
  ...rest
}: SelectFieldProps) {
  return (
    <Field label={label} hint={hint} error={error} required={rest.required}>
      {({ controlId, describedBy }) => (
        <div className="relative">
          <select
            id={controlId}
            aria-describedby={describedBy}
            aria-invalid={error ? true : undefined}
            className={controlClasses(Boolean(error), cn("h-11 appearance-none pr-9", className))}
            {...rest}
          >
            {placeholder && <option value="">{placeholder}</option>}
            {options.map((option) => (
              <option key={option.value} value={option.value} disabled={option.disabled}>
                {option.label}
              </option>
            ))}
          </select>
          <svg
            className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-fg-3"
            viewBox="0 0 16 16"
            fill="none"
            aria-hidden
          >
            <path
              d="M4 6l4 4 4-4"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
      )}
    </Field>
  );
}

export type CheckboxProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "id"> & {
  label: ReactNode;
  error?: string;
};

export function Checkbox({ label, error, className, ...rest }: CheckboxProps) {
  const id = useId();
  const errorId = `${id}-error`;

  return (
    <div className="space-y-1.5">
      <div className="flex items-start gap-2.5">
        <input
          id={id}
          type="checkbox"
          aria-describedby={error ? errorId : undefined}
          aria-invalid={error ? true : undefined}
          className={cn(
            "mt-0.5 size-4.5 shrink-0 rounded border-line-strong text-accent",
            "accent-[var(--primary)]",
            error && "border-bad",
            className,
          )}
          {...rest}
        />
        <label htmlFor={id} className="text-sm leading-snug text-fg-2">
          {label}
        </label>
      </div>
      {error && (
        <p id={errorId} role="alert" className="text-xs text-bad">
          {error}
        </p>
      )}
    </div>
  );
}
