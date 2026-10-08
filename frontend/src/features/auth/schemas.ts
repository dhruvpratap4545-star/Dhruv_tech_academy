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

export const password = z
  .string()
  .min(8, "Use at least 8 characters.")
  .max(128, "Use at most 128 characters.")
  .refine((value) => /[A-Za-z]/.test(value), "Include at least one letter.")
  .refine((value) => /\d/.test(value), "Include at least one number.")
  .refine((value) => !COMMON_PASSWORDS.has(value.toLowerCase()), "That password is too common.");

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
