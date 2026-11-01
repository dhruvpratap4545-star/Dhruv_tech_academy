import { useCurrentUser } from "@/features/auth/useAuth";
import type { Language, MessageKey } from "@/lib/i18n";
import { asLanguage, translate } from "@/lib/i18n";

/** `t("key", {vars})` in the signed-in person's language. */
export function useT(): {
  t: (key: MessageKey, vars?: Record<string, string | number>) => string;
  language: Language;
} {
  const language = asLanguage(useCurrentUser()?.preferences.language);
  return { t: (key, vars) => translate(language, key, vars), language };
}
