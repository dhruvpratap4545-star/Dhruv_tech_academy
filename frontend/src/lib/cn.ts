/**
 * Join class names, dropping falsy values.
 *
 * Deliberately not `clsx` + `tailwind-merge`: the component set below never passes
 * conflicting utilities for the same property, so the extra dependency and its runtime
 * cost would buy nothing.
 */
export function cn(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}
