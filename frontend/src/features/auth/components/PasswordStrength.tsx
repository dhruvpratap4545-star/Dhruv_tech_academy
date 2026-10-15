import type { Control, FieldValues, Path } from "react-hook-form";
import { useWatch } from "react-hook-form";

import { Icon } from "@/components/Icon";
import { PASSWORD_RULES } from "@/features/auth/schemas";
import { cn } from "@/lib/cn";

/**
 * The password rules, ticked off as they are met.
 *
 * Shown before the field is submitted rather than after it is rejected. Someone choosing a
 * password is making one decision; telling them the rules only once they have guessed
 * wrong turns it into several, and the usual outcome is an old password reused.
 *
 * Driven from `PASSWORD_RULES`, the same list the zod schema validates against — a
 * checklist that can tick every box while the form still refuses the password is worse
 * than showing nothing.
 *
 * It is announced politely: `aria-live="polite"` on a list that changes under the field
 * someone is typing in, so a screen reader reports progress without interrupting them
 * mid-word.
 */
export function PasswordStrength<T extends FieldValues>({
  control,
  name,
  className,
}: {
  control: Control<T>;
  name: Path<T>;
  className?: string;
}) {
  // `useWatch` rather than `form.watch()`: watch() re-renders the whole form on every
  // keystroke and makes the React Compiler bail out of the component that calls it. This
  // subscribes to one field, here, and leaves the forms themselves optimisable.
  const value = (useWatch({ control, name }) as string | undefined) ?? "";
  const met = PASSWORD_RULES.filter((rule) => rule.test(value)).length;
  const all = met === PASSWORD_RULES.length;

  return (
    <div className={cn("rounded-md border border-line bg-surface-2 p-3", className)}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold text-fg-2">Your password needs</p>
        <p
          className={cn("num text-xs font-semibold", all ? "text-ok" : "text-fg-3")}
          aria-hidden="true"
        >
          {met} / {PASSWORD_RULES.length}
        </p>
      </div>

      <ul className="mt-2 space-y-1" aria-live="polite">
        {PASSWORD_RULES.map((rule) => {
          const ok = rule.test(value);
          return (
            <li key={rule.label} className="flex items-center gap-2 text-xs">
              <span className={cn("shrink-0", ok ? "text-ok" : "text-fg-3")}>
                {ok ? (
                  <Icon name="check" className="size-3.5" />
                ) : (
                  // A hollow ring, not a cross: nothing has gone wrong yet, this is simply
                  // a step still to come.
                  <span className="block size-3.5 rounded-full border-[1.5px] border-current" />
                )}
              </span>
              <span className={ok ? "text-fg-2" : "text-fg-3"}>{rule.label}</span>
              <span className="sr-only">{ok ? " — done" : " — still needed"}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
