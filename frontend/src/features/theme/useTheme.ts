import { useCallback, useEffect, useState } from "react";

import type { Theme } from "@/features/auth/types";

/**
 * Light / Dark / System (PRD §4.6).
 *
 * Two places remember the choice, for different reasons:
 *
 * * `localStorage`, read by an inline script in index.html *before* React mounts, so the
 *   page never flashes white before a dark theme applies;
 * * the server, via `PATCH /me/preferences`, so the choice follows the user to any device
 *   (PRD §13 criterion 10).
 *
 * The server copy wins when a session starts; localStorage is only the anti-flash cache.
 */

const STORAGE_KEY = "dhruv-theme";

export function isTheme(value: unknown): value is Theme {
  return value === "light" || value === "dark" || value === "system";
}

function prefersDark(): boolean {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

export function applyTheme(theme: Theme): void {
  const dark = theme === "dark" || (theme === "system" && prefersDark());
  document.documentElement.classList.toggle("dark", dark);
}

export function readStoredTheme(): Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return isTheme(stored) ? stored : "system";
  } catch {
    // Private windows and blocked site data both throw here. Not a reason to fail.
    return "system";
  }
}

function storeTheme(theme: Theme): void {
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* ignore — the server copy is the durable one */
  }
}

export function useTheme(onPersist?: (theme: Theme) => void) {
  const [theme, setThemeState] = useState<Theme>(readStoredTheme);

  useEffect(() => {
    applyTheme(theme);
    storeTheme(theme);
  }, [theme]);

  // Only "system" tracks the OS. An explicit choice must not be overridden at sunset.
  useEffect(() => {
    if (theme !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme("system");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [theme]);

  const setTheme = useCallback(
    (next: Theme) => {
      setThemeState(next);
      onPersist?.(next);
    },
    [onPersist],
  );

  /** Adopt the server's saved preference when `/me` arrives, without a write back. */
  const adoptTheme = useCallback((next: Theme) => setThemeState(next), []);

  return { theme, setTheme, adoptTheme };
}
