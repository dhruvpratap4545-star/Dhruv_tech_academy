import { useMutation } from "@tanstack/react-query";

import { updatePreferences } from "@/features/auth/api";
import { useInvalidateMe } from "@/features/auth/useAuth";
import { useT } from "@/features/i18n/useT";
import { LANGUAGES } from "@/lib/i18n";
import { cn } from "@/lib/cn";

/**
 * English / हिन्दी, saved to the person's preferences so it follows them across devices.
 * Shown on the Phase 3 screens, which are the ones that are translated.
 */
export function LanguageToggle() {
  const { t, language } = useT();
  const invalidateMe = useInvalidateMe();
  const save = useMutation({
    mutationFn: (value: string) => updatePreferences({ language: value }),
    onSuccess: () => invalidateMe(),
  });

  return (
    <fieldset className="inline-flex rounded-lg border border-line bg-surface p-0.5">
      <legend className="sr-only">{t("common.language")}</legend>
      {LANGUAGES.map((option) => {
        const active = language === option.value;
        return (
          <label
            key={option.value}
            className={cn(
              "cursor-pointer rounded-md px-2.5 py-1.5 text-xs font-medium",
              active ? "bg-accent text-accent-fg" : "text-fg-2 hover:bg-surface-2 hover:text-fg",
            )}
          >
            <input
              type="radio"
              name="language"
              value={option.value}
              checked={active}
              disabled={save.isPending}
              onChange={() => save.mutate(option.value)}
              className="sr-only"
            />
            {option.label}
          </label>
        );
      })}
    </fieldset>
  );
}
