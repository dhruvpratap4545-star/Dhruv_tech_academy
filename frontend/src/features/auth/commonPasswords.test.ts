import { describe, expect, it } from "vitest";

import fixture from "@/features/auth/commonPasswords.fixture.json";
import { isCommonPassword } from "@/features/auth/commonPasswords";
import { password } from "@/features/auth/schemas";

/**
 * The browser's answer has to be the server's answer, for every case.
 *
 * The fixture is not written by hand: `backend/scripts/make_common_passwords.py` produces
 * it by calling the real Python `is_common` on each password. So this is not two
 * implementations agreeing with a list somebody typed — it is this implementation being
 * held to what the server actually does.
 *
 * The failure this prevents is specific and nasty: a live checklist showing every rule
 * satisfied, and then a 422 from the API saying the password is too common, with nothing
 * on screen explaining the contradiction.
 */
describe("the common-password check matches the server", () => {
  it("has a fixture with both kinds of case in it", () => {
    expect(fixture.cases.length).toBeGreaterThan(40);
    expect(fixture.cases.some((c) => c.common)).toBe(true);
    expect(fixture.cases.some((c) => !c.common)).toBe(true);
  });

  for (const testCase of fixture.cases) {
    const verdict = testCase.common ? "refuses" : "accepts";
    it(`${verdict} ${JSON.stringify(testCase.password)}`, () => {
      expect(isCommonPassword(testCase.password)).toBe(testCase.common);
    });
  }
});

describe("the zod schema uses the same check", () => {
  it("rejects a listed password through the form schema, not just the helper", () => {
    const result = password.safeParse("P@ssw0rd123");
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.map((i) => i.message).join(" ")).toMatch(/too common/i);
    }
  });

  it("accepts a password that only looks like a listed one", () => {
    // "root" is on the list; "beetroot" is not, and the difference is the whole point.
    expect(password.safeParse("Beetroot2026!").success).toBe(true);
  });
});
