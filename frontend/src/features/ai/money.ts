/** Rupees as typed in a form, to paise for the API. Empty means "no limit". */
export function rupeesToPaise(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const number = Number(trimmed.replace(/,/g, ""));
  return Number.isFinite(number) && number >= 0 ? Math.round(number * 100) : null;
}

export function paiseToRupees(value: number | null | undefined): string {
  return value == null ? "" : String(value / 100);
}
