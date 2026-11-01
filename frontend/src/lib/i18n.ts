/**
 * English and Hindi for the Phase 3 screens, without an i18n library.
 *
 * A dictionary and a lookup are all these screens need: no plural rules beyond what a
 * sentence can avoid, no runtime loading, nothing to configure. The language comes from
 * the signed-in person's saved preference (`preferences.language`), so it follows them
 * across devices like the theme does.
 *
 * Only the new screens use this (Milestone 1 scope). Translating the existing admin
 * screens is a separate piece of work, so a key missing here falls back to English rather
 * than failing — a half-translated screen is better than a broken one.
 *
 * Hindi strings are a first draft and are to be reviewed by a native speaker before
 * launch (prerequisite 12).
 */

import { HOMEWORK_EN, HOMEWORK_HI } from "@/features/homework/messages";
import { LIBRARY_EN, LIBRARY_HI } from "@/features/library/messages";

export type Language = "en" | "hi";

export const LANGUAGES: { value: Language; label: string }[] = [
  { value: "en", label: "English" },
  { value: "hi", label: "हिन्दी" },
];

const CORE_EN = {
  // Shared
  "common.save": "Save",
  "common.saving": "Saving…",
  "common.saved": "Saved",
  "common.cancel": "Cancel",
  "common.edit": "Edit",
  "common.on": "On",
  "common.off": "Off",
  "common.loading": "Loading…",
  "common.none": "None",
  "common.download": "Download",
  "common.export": "Export to Excel",
  "common.all": "All",
  "common.language": "Language",
  // File upload
  "upload.choose": "Choose files",
  "upload.camera": "Take a photo",
  "upload.hint": "PDF, JPG or PNG, up to {mb} MB each. Up to {max} files.",
  "upload.tooBig": "{name} is larger than {mb} MB.",
  "upload.wrongType": "{name} is not a PDF, JPG or PNG.",
  "upload.tooMany": "You can attach at most {max} files.",
  "upload.remove": "Remove {name}",
  // Modules
  "modules.title": "Modules",
  "modules.description": "Optional modules switched on for this institute.",
  // AI Control Room
  "ai.eyebrow": "AI Control Room",
  "ai.nav.dashboard": "Dashboard",
  "ai.nav.models": "Providers & models",
  "ai.nav.features": "Features",
  "ai.nav.budgets": "Budgets & limits",
  "ai.nav.usage": "Usage log",
  "ai.nav.playground": "Playground",
  "ai.dashboard.title": "AI usage",
  "ai.dashboard.description": "Spend against budget, and where it goes, in your scope.",
  "ai.today": "Today",
  "ai.month": "This month",
  "ai.requests": "Requests",
  "ai.tokens": "Tokens",
  "ai.cost": "Cost",
  "ai.blocked": "Blocked",
  "ai.errors": "Errors",
  "ai.byFeature": "By feature",
  "ai.byInstitute": "By institute",
  "ai.trend": "Last 30 days",
  "ai.budget": "Budget",
  "ai.noBudget": "No budget set — only the platform budget applies.",
  "ai.used": "{used} of {limit} used",
  "ai.globalSwitch": "AI on the platform",
  "ai.globalSwitchHint": "The master kill switch. Turning it off stops every AI request at once.",
  "ai.playground.title": "Playground",
  "ai.playground.description":
    "Send a test prompt through every control — switches, limits, budgets, redaction. It is logged like any other request.",
  "ai.playground.prompt": "Prompt",
  "ai.playground.institute": "Charge to institute",
  "ai.playground.platform": "Platform (no institute)",
  "ai.playground.run": "Run prompt",
  "ai.playground.answer": "Answer",
} as const;

// Each feature keeps its own strings beside its screens; they are merged here.
const EN = { ...CORE_EN, ...LIBRARY_EN, ...HOMEWORK_EN };

export type MessageKey = keyof typeof EN;

const CORE_HI: Partial<Record<MessageKey, string>> = {
  "common.save": "सहेजें",
  "common.saving": "सहेजा जा रहा है…",
  "common.saved": "सहेज लिया गया",
  "common.cancel": "रद्द करें",
  "common.edit": "बदलें",
  "common.on": "चालू",
  "common.off": "बंद",
  "common.loading": "लोड हो रहा है…",
  "common.none": "कोई नहीं",
  "common.download": "डाउनलोड करें",
  "common.export": "एक्सेल में निकालें",
  "common.all": "सभी",
  "common.language": "भाषा",
  "upload.choose": "फ़ाइलें चुनें",
  "upload.camera": "फ़ोटो लें",
  "upload.hint": "PDF, JPG या PNG, हर फ़ाइल {mb} MB तक। अधिकतम {max} फ़ाइलें।",
  "upload.tooBig": "{name} {mb} MB से बड़ी है।",
  "upload.wrongType": "{name} PDF, JPG या PNG नहीं है।",
  "upload.tooMany": "आप अधिकतम {max} फ़ाइलें जोड़ सकते हैं।",
  "upload.remove": "{name} हटाएँ",
  "modules.title": "मॉड्यूल",
  "modules.description": "इस संस्थान के लिए चालू किए गए वैकल्पिक मॉड्यूल।",
  "ai.eyebrow": "AI नियंत्रण कक्ष",
  "ai.nav.dashboard": "डैशबोर्ड",
  "ai.nav.models": "प्रदाता और मॉडल",
  "ai.nav.features": "सुविधाएँ",
  "ai.nav.budgets": "बजट और सीमाएँ",
  "ai.nav.usage": "उपयोग लॉग",
  "ai.nav.playground": "प्लेग्राउंड",
  "ai.dashboard.title": "AI उपयोग",
  "ai.dashboard.description": "बजट के मुकाबले खर्च, और वह कहाँ जा रहा है।",
  "ai.today": "आज",
  "ai.month": "इस महीने",
  "ai.requests": "अनुरोध",
  "ai.tokens": "टोकन",
  "ai.cost": "लागत",
  "ai.blocked": "रोके गए",
  "ai.errors": "त्रुटियाँ",
  "ai.byFeature": "सुविधा के अनुसार",
  "ai.byInstitute": "संस्थान के अनुसार",
  "ai.trend": "पिछले 30 दिन",
  "ai.budget": "बजट",
  "ai.noBudget": "कोई बजट तय नहीं — केवल प्लेटफ़ॉर्म बजट लागू है।",
  "ai.used": "{limit} में से {used} उपयोग हुआ",
  "ai.globalSwitch": "प्लेटफ़ॉर्म पर AI",
  "ai.globalSwitchHint": "मुख्य स्विच। इसे बंद करते ही हर AI अनुरोध रुक जाता है।",
  "ai.playground.title": "प्लेग्राउंड",
  "ai.playground.description":
    "हर नियंत्रण से होकर एक परीक्षण प्रॉम्प्ट भेजें। यह बाकी अनुरोधों की तरह दर्ज होता है।",
  "ai.playground.prompt": "प्रॉम्प्ट",
  "ai.playground.institute": "किस संस्थान के खाते में",
  "ai.playground.platform": "प्लेटफ़ॉर्म (कोई संस्थान नहीं)",
  "ai.playground.run": "प्रॉम्प्ट चलाएँ",
  "ai.playground.answer": "उत्तर",
};

const HI: Partial<Record<MessageKey, string>> = { ...CORE_HI, ...LIBRARY_HI, ...HOMEWORK_HI };

const DICTIONARIES: Record<Language, Partial<Record<MessageKey, string>>> = { en: EN, hi: HI };

export function asLanguage(value: string | null | undefined): Language {
  return value === "hi" ? "hi" : "en";
}

/** Look a key up, falling back to English, and fill `{placeholders}`. */
export function translate(
  language: Language,
  key: MessageKey,
  vars?: Record<string, string | number>,
): string {
  const template = DICTIONARIES[language][key] ?? EN[key];
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in vars ? String(vars[name]) : match,
  );
}
