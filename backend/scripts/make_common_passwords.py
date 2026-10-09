"""Regenerate the browser's copy of the common-password check.

The list and the matching rules exist twice — once in Python, where they decide, and once
in TypeScript, where they give the person typing immediate feedback. Two hand-maintained
copies drift, and the way that failure shows up is the worst kind: a live checklist with
every box ticked green, and an API that refuses the password anyway, with no clue why.

So the TypeScript is generated from the Python and never edited by hand.

    cd backend && python scripts/make_common_passwords.py

``tests/test_common_passwords.py`` reads the generated file and fails if it no longer
matches, so forgetting to run this breaks the build rather than the sign-up form.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.modules.auth.passwords import (
    COMMON_PASSWORDS,
    LEET,
    MIN_COVERAGE,
    MIN_WORD_LENGTH,
)

TARGET = (
    pathlib.Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "features"
    / "auth"
    / "commonPasswords.ts"
)

HEADER = """/**
 * The "that password is too common" check, in the browser.
 *
 * A live checklist that ticks every box and is then refused by the API is worse than no
 * checklist at all, so this is a character-for-character mirror of
 * `backend/app/modules/auth/passwords.py`.
 *
 * GENERATED FILE — do not edit. Run `python scripts/make_common_passwords.py` in `backend`
 * after changing the Python. `backend/tests/test_common_passwords.py` fails the build if
 * the two ever disagree.
 *
 * The backend still decides. This exists so the person typing finds out now rather than
 * after a round trip.
 */
"""

BODY = r"""
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
 * readings are plausible, so both are tried.
 */
export function undecorateDigitsOnly(value: string): string {
  return [...value.toLowerCase()]
    .map((ch) => (isDigit(ch) ? (LEET[ch] ?? ch) : ch))
    .filter(isAlnum)
    .join("");
}

const TRAILING_DIGITS = /\d+$/;

/**
 * Every reading of `value` worth checking.
 *
 * There is no single correct normalisation, because the same character means different
 * things in different passwords: `!` is an `i` in `l3tm31n!` and an exclamation mark in
 * `Password!`. Rather than guess, every plausible reading is produced and the password is
 * refused if any of them is a known-common one.
 */
export function candidates(value: string): string[] {
  const lowered = value.toLowerCase();
  const plain = [...lowered].filter(isAlnum).join("");

  const forms = [lowered, plain, undecorate(value), undecorateDigitsOnly(value)];
  for (const base of [value, plain]) {
    const stripped = base.replace(TRAILING_DIGITS, "");
    if (stripped && stripped !== base) {
      forms.push(stripped.toLowerCase(), undecorate(stripped), undecorateDigitsOnly(stripped));
    }
  }
  return forms.filter(Boolean);
}

/**
 * True when the password is a known-common one wearing a disguise.
 *
 * Exact matching alone is not enough: `$h1va@2026` is "Shiva" with a dollar sign, a one and
 * this year stuck on the end, and no normalisation turns it into exactly `shiva`. So each
 * reading is also searched for a listed word inside it, subject to two conditions — the
 * word has to be at least `MIN_WORD_LENGTH` characters, so short names do not fire inside
 * longer ones, and it has to make up at least `MIN_COVERAGE` of what was typed.
 */
export function isCommonPassword(value: string): boolean {
  const forms = candidates(value);
  if (forms.some((form) => COMMON_PASSWORDS.has(form))) return true;

  for (const form of forms) {
    const threshold = form.length * MIN_COVERAGE;
    for (const word of COMMON_PASSWORDS) {
      if (word.length >= MIN_WORD_LENGTH && word.length >= threshold && form.includes(word)) {
        return true;
      }
    }
  }
  return false;
}
"""


def render() -> str:
    leet = "\n".join(f'  "{key}": "{value}",' for key, value in LEET.items())
    words = "\n".join(f'  "{word}",' for word in sorted(COMMON_PASSWORDS))
    return (
        HEADER + "\n/** Characters people substitute to satisfy a symbol rule without changing the"
        " word. */\nexport const LEET: Record<string, string> = {\n" + leet + "\n};\n\n"
        '/** A matched word must be at least this long, or "ravi" would fire inside'
        ' "travinder". */\n'
        f"export const MIN_WORD_LENGTH = {MIN_WORD_LENGTH};\n\n"
        "/**\n * ...and must account for at least this much of the password, or one common"
        " word buried in\n * a genuinely long passphrase would be refused for no reason.\n"
        " */\n"
        f"export const MIN_COVERAGE = {MIN_COVERAGE};\n\n"
        "export const COMMON_PASSWORDS: ReadonlySet<string> = new Set([\n"
        + words
        + "\n]);\n"
        + BODY
    )


def main() -> None:
    TARGET.write_text(render(), encoding="utf-8")
    print(f"wrote {TARGET} ({len(COMMON_PASSWORDS)} words)")


if __name__ == "__main__":
    main()
