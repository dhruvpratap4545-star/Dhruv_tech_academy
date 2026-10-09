import { describe, expect, it } from "vitest";

import { PASSWORD_RULES, password } from "@/features/auth/schemas";

/**
 * The browser's copy of the password policy.
 *
 * It exists to give immediate feedback, never to be the decision — the backend enforces
 * the same four rules in `app/modules/auth/schemas.py`. What these tests protect is the
 * agreement between the two. A checklist that ticks every box while the server refuses
 * the password is worse than showing no checklist at all.
 */
describe("password rules", () => {
  const check = (value: string) => PASSWORD_RULES.filter((r) => r.test(value)).map((r) => r.label);

  it("requires all four things", () => {
    expect(check("Correct-Horse9")).toHaveLength(4);
    expect(check("short1!")).not.toContain("At least 8 characters");
    expect(check("12345678!")).not.toContain("One letter");
    expect(check("abcdefgh!")).not.toContain("One number");
    expect(check("abcdefgh1")).not.toContain("One special character");
  });

  it("counts letters in any script, not just Latin", () => {
    // This platform is Indian. An ASCII-only rule would tell someone whose password is in
    // Kannada that it contains no letter, and then count those letters as symbols.
    expect(check("ಕನ್ನಡ123!")).toHaveLength(4);
    expect(check("देवनागरी12#")).toHaveLength(4);
  });

  it("treats a space as a special character", () => {
    // Rejecting a passphrase for containing a space would push people towards shorter,
    // worse passwords.
    expect(check("my dog is 7")).toContain("One special character");
  });

  it("accepts what the rules describe", () => {
    expect(password.safeParse("Correct-Horse9").success).toBe(true);
    expect(password.safeParse("Tr0ub4dor&3").success).toBe(true);
  });

  it("refuses a common password with a symbol bolted on", () => {
    // The one evasion a character-class rule invites. "password123!" is no stronger than
    // "password123" against anyone running a wordlist with mangling rules.
    expect(password.safeParse("password123!").success).toBe(false);
    expect(password.safeParse("Admin123#").success).toBe(false);
  });

  it("names every rule a password breaks, not just the first", () => {
    const result = password.safeParse("abc");
    expect(result.success).toBe(false);
    if (!result.success) {
      const messages = result.error.issues.map((i) => i.message).join(" ");
      expect(messages).toContain("8 characters");
      expect(messages).toContain("number");
      expect(messages).toContain("special character");
    }
  });
});
