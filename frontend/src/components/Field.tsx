import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { useId } from "react";

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
  return (
    <Field label={label} hint={hint} error={error} required={rest.required} action={action}>
      {({ controlId, describedBy }) => (
        <input
          id={controlId}
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
          className={controlClasses(Boolean(error), cn("h-11", className))}
          {...rest}
        />
      )}
    </Field>
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
