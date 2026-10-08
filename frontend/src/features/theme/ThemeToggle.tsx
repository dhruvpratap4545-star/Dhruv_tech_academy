import { useMutation } from "@tanstack/react-query";

import { updatePreferences } from "@/features/auth/api";
import type { Theme } from "@/features/auth/types";
import { useTheme } from "@/features/theme/useTheme";
import { cn } from "@/lib/cn";

const OPTIONS: { value: Theme; label: string; icon: string }[] = [
  {
    value: "light",
    label: "Light",
    icon: "M8 2v1.5M8 12.5V14M14 8h-1.5M3.5 8H2m9.3-4.3-1 1m-4.6 4.6-1 1m6.6 0-1-1M5.7 5.7l-1-1M11 8a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z",
  },
  { value: "dark", label: "Dark", icon: "M13 9.5A5.5 5.5 0 0 1 6.5 3a5.5 5.5 0 1 0 6.5 6.5Z" },
  { value: "system", label: "System", icon: "M2.5 3.5h11v7h-11v-7ZM6 13h4" },
];

/**
 * Saves to the server when the user is signed in, so the choice follows them.
 * A failed save is not surfaced: the theme has already applied locally, and interrupting
 * someone with an error banner because their colour preference did not sync would be worse
 * than the preference quietly reverting on another device.
 */
export function ThemeToggle({ persist = true }: { persist?: boolean }) {
  const save = useMutation({
    mutationFn: (theme: Theme) => updatePreferences({ theme }),
  });
  const { theme, setTheme } = useTheme(persist ? (next) => save.mutate(next) : undefined);

  return (
    <fieldset className="inline-flex rounded-lg border border-line bg-surface p-0.5">
      <legend className="sr-only">Theme</legend>
      {OPTIONS.map((option) => {
        const active = theme === option.value;
        return (
          <label
            key={option.value}
            title={option.label}
            className={cn(
              "flex cursor-pointer items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium",
              "transition-colors duration-(--duration-fast)",
              active ? "bg-accent text-accent-fg" : "text-fg-2 hover:bg-surface-2 hover:text-fg",
            )}
          >
            <input
              type="radio"
              name="theme"
              value={option.value}
              checked={active}
              onChange={() => setTheme(option.value)}
              className="sr-only"
            />
            <svg viewBox="0 0 16 16" className="size-3.5" fill="none" aria-hidden>
              <path
                d={option.icon}
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span className="hidden sm:inline">{option.label}</span>
          </label>
        );
      })}
    </fieldset>
  );
}
