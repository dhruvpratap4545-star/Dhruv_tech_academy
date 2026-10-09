import { COMMON_PASSWORDS, LEET } from "@/features/auth/commonPasswordList";

/**
 * The "that password is too common" check, in the browser.
 *
 * A mirror of `backend/app/modules/auth/passwords.py`. The backend still decides; this
 * exists so the person typing finds out now rather than after a round trip, and a live
 * checklist that goes all green and is then refused by the API is worse than no checklist
 * at all.
 *
 * The word list and the substitution table are generated from the Python
 * (`commonPasswordList.ts`). The algorithm below is written by hand so it can be read and
 * reviewed like any other code — and `commonPasswords.test.ts` runs it against a fixture
 * of answers produced by calling the real Python function, so the two cannot drift apart
 * without the build failing.
 *
 * Four structural rules — length, a letter, a digit, a symbol — stop almost nothing on
 * their own, because the passwords people actually choose satisfy all four. `Password123!`
 * is twelve characters with a letter, a digit and a symbol, and it is among the most
 * guessed strings in the world. So the rules are paired with a list, and the list is only
 * useful if it sees through the decoration people add to get past the rules.
 */

const isAlnum = (ch: string) => /[\p{L}\p{Nd}]/u.test(ch);
const isDigit = (ch: string) => /\p{Nd}/u.test(ch);

/** Fold every substitution back to a letter, then keep only letters and digits. */
export function undecorate(value: string): string {
  return [...value.toLowerCase()]
    .map((ch) => LEET[ch] ?? ch)
    .filter(isAlnum)
    .join("");
}

/**
 * Fold the digit substitutions, but throw the symbols away instead of folding them.
 *
 * `l3tm31n!` needs this. Folding everything turns the final `!` into an `i` and produces
 * `letmeini`; folding only the digits and discarding the punctuation gives `letmein`. Both
 * readings are plausible — `!` really is used for `i` mid-word, and it is also just an
 * exclamation mark on the end — so both are tried.
 */
export function undecorateDigitsOnly(value: string): string {
  return [...value.toLowerCase()]
    .map((ch) => (isDigit(ch) ? (LEET[ch] ?? ch) : ch))
    .filter(isAlnum)
    .join("");
}

const TRAILING_DIGITS = /\d+$/;
const LEADING_DECORATION = /^[^A-Za-z]+/;
const TRAILING_DECORATION = /[^A-Za-z]+$/;

/**
 * `value` with its leading decoration gone, its trailing decoration gone, and both.
 *
 * All three, because an edge symbol is ambiguous and nothing in the string says which it
 * is. In `$h1va@2026` the leading `$` is the `S` of "Shiva" and has to be folded, while
 * the trailing `@2026` is padding and has to be cut. Cutting both ends gives `h1va` —
 * "hiva", which is nothing; cutting only the trailing end leaves `$h1va`, which folds to
 * exactly `shiva`. `2026@Dhruv` needs the mirror image.
 */
export function trimmedEdges(value: string): string[] {
  return [
    value.replace(TRAILING_DECORATION, ""),
    value.replace(LEADING_DECORATION, ""),
    value.replace(TRAILING_DECORATION, "").replace(LEADING_DECORATION, ""),
  ];
}

/**
 * Every reading of `value` worth checking.
 *
 * There is no single correct normalisation, because the same character means different
 * things in different passwords: `0` is an `o` in `passw0rd` and a zero in `Student2026`.
 * Rather than guess, every plausible reading is produced.
 */
export function candidates(value: string): string[] {
  const lowered = value.toLowerCase();
  const plain = [...lowered].filter(isAlnum).join("");

  const forms = [lowered, plain, undecorate(value), undecorateDigitsOnly(value)];
  for (const base of [value, plain]) {
    for (const cut of [base.replace(TRAILING_DIGITS, ""), ...trimmedEdges(base)]) {
      if (cut && cut !== base) {
        forms.push(cut.toLowerCase(), undecorate(cut), undecorateDigitsOnly(cut));
      }
    }
  }
  return forms.filter(Boolean);
}

/**
 * True when the password is a known-common one wearing a disguise.
 *
 * Exact matching, against every reading `candidates` produces. There is deliberately no
 * substring search: one was tried, and it refused `Beetroot2026!` because "root" is on the
 * list, along with `Examiner7#`, `Masterclass9!` and `Dragonfly-9!`. A check that refuses
 * good passwords teaches people to fight the form, and what they produce on the fourth
 * attempt is reliably worse than what they started with.
 */
export function isCommonPassword(value: string): boolean {
  return candidates(value).some((form) => COMMON_PASSWORDS.has(form));
}
