import { z } from "zod";

/**
 * Mirrors the backend rules (PRD §7.1) so the user is told immediately rather than after a
 * round trip. The backend validates independently — this is for speed, not for safety.
 */

const COMMON_PASSWORDS = new Set([
  "password",
  "password1",
  "password123",
  "12345678",
  "123456789",
  "1234567890",
  "qwerty123",
  "abc12345",
  "iloveyou",
  "admin123",
  "welcome1",
  "letmein1",
  "dhruv123",
  "academy123",
]);

/**
 * The four rules, as one list.
 *
 * Exported so the live checklist and the zod schema cannot drift: a form that ticks every
 * box and then fails validation is worse than no checklist at all. The backend enforces
 * the same four in `app/modules/auth/schemas.py` — this copy exists to give immediate
 * feedback, never to be the decision.
 */
export const PASSWORD_RULES = [
  { label: "At least 8 characters", test: (v: string) => v.length >= 8 },
  // Unicode classes, not ASCII ones. This platform is Indian: `[A-Za-z]` would tell
  // somebody whose password is in Kannada or Devanagari that it has no letter, and then
  // count those same letters as special characters. The backend uses Python's `str`
  // methods, which are Unicode-aware for the same reason.
  { label: "One letter", test: (v: string) => /\p{L}/u.test(v) },
  { label: "One number", test: (v: string) => /\p{N}/u.test(v) },
  // Anything that is neither, spaces included. Listing "allowed symbols" is how a
  // password manager's output gets rejected for a character nobody thought of.
  { label: "One special character", test: (v: string) => /[^\p{L}\p{N}]/u.test(v) },
] as const;

/** Strip the decoration before the common check: "password123!" is not a new password. */
const undecorate = (value: string) => value.replace(/[^\p{L}\p{N}]/gu, "").toLowerCase();

export const password = z
  .string()
  .max(128, "Use at most 128 characters.")
  .superRefine((value, ctx) => {
    for (const rule of PASSWORD_RULES) {
      if (!rule.test(value)) {
        ctx.addIssue({ code: "custom", message: `Password needs: ${rule.label.toLowerCase()}.` });
      }
    }
  })
  .refine(
    (value) => !COMMON_PASSWORDS.has(value.toLowerCase()) && !COMMON_PASSWORDS.has(undecorate(value)),
    "That password is too common.",
  );

export const email = z
  .string()
  .min(1, "Enter your email address.")
  .email("Enter a valid email address.");

export const loginSchema = z.object({
  email,
  password: z.string().min(1, "Enter your password."),
  remember_me: z.boolean(),
});

export const registerSchema = z.object({
  full_name: z.string().min(2, "Enter your full name.").max(120, "That name is too long."),
  email,
  password,
  accept_terms: z.literal(true, { message: "Please accept the terms to continue." }),
});

export const forgotSchema = z.object({ email });

export const otpSchema = z.object({
  code: z
    .string()
    .trim()
    .regex(/^\d{6}$/, "Enter the 6-digit code from your email."),
});

export const newPasswordSchema = z
  .object({ new_password: password, confirm_password: z.string() })
  .refine((values) => values.new_password === values.confirm_password, {
    message: "Both passwords must match.",
    path: ["confirm_password"],
  });

export const setupSchema = z
  .object({
    email,
    code: z
      .string()
      .trim()
      .regex(/^\d{6}$/, "Enter the 6-digit code from your email."),
    new_password: password,
    confirm_password: z.string(),
  })
  .refine((values) => values.new_password === values.confirm_password, {
    message: "Both passwords must match.",
    path: ["confirm_password"],
  });

export const changePasswordSchema = z
  .object({
    current_password: z.string().min(1, "Enter your current password."),
    new_password: password,
    confirm_password: z.string(),
  })
  .refine((values) => values.new_password === values.confirm_password, {
    message: "Both passwords must match.",
    path: ["confirm_password"],
  })
  .refine((values) => values.current_password !== values.new_password, {
    message: "Your new password must be different from the current one.",
    path: ["new_password"],
  });

export type LoginValues = z.infer<typeof loginSchema>;
export type RegisterValues = z.infer<typeof registerSchema>;
export type ForgotValues = z.infer<typeof forgotSchema>;
export type OtpValues = z.infer<typeof otpSchema>;
export type NewPasswordValues = z.infer<typeof newPasswordSchema>;
export type SetupValues = z.infer<typeof setupSchema>;
export type ChangePasswordValues = z.infer<typeof changePasswordSchema>;
