"""Regenerate what the browser needs to run the common-password check.

The check exists twice — once in Python, where it decides, and once in TypeScript, where it
gives the person typing immediate feedback. Two copies drift, and the way that failure
shows up is the worst kind: a live checklist with every box green, and an API that refuses
the password anyway.

Rather than generate the TypeScript *algorithm* from Python — which only moves the drift
into a string literal nobody reviews — this writes two things and leaves the algorithm to
be written and reviewed like any other code:

``frontend/src/features/auth/commonPasswordList.ts``
    The data: the substitution table and the word list. Generated, never edited by hand.

``frontend/src/features/auth/commonPasswords.fixture.json``
    A table of passwords and the answer Python gives for each, produced by calling the real
    `is_common`. The TypeScript has to reproduce every one of those answers, which is a
    test of behaviour rather than of text.

Run it after changing anything in `app/modules/auth/passwords.py`::

    cd backend && python scripts/make_common_passwords.py

`tests/test_common_passwords.py` fails the build if the generated files are stale, and
`frontend/src/features/auth/commonPasswords.test.ts` fails if the browser disagrees with
the fixture.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.modules.auth.passwords import COMMON_PASSWORDS, LEET, is_common

FRONTEND = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "features" / "auth"
LIST_FILE = FRONTEND / "commonPasswordList.ts"
FIXTURE_FILE = FRONTEND / "commonPasswords.fixture.json"

#: Passwords that must be refused: a listed word with the decoration people add to get past
#: a character-class rule. Every one satisfies length, letter, digit and symbol, which is
#: exactly why those four rules are not enough on their own.
MUST_REFUSE = [
    "password",
    "Password123!",
    "P@ssw0rd123",
    "passw0rd00",
    "...Password...",
    "Dhruv@2026",
    "Dhruv!2026",
    "2026@Dhruv",
    "Academy@123",
    "@cademy99",
    "Student@2026",
    "$tudent2026",
    "Sachin$123",
    "Krishna@108",
    "Jaishreeram@1",
    "$h1va@2026",
    "Ravi@2026",
    "#Pooja1234",
    "mumbai@123",
    "qwerty99",
    "Qw3rty!2026",
    "zxcvbnm1",
    "1qaz2wsx",
    "l3tm31n!",
    "Adm1n@123",
    "Admin@2026",
    "C0mput3r#1",
    "Cr1cket!99",
    "Cricket@111",
    "iloveyou143",
    "12345678",
    "Abcdefg1!",
    # A single letter after the decoration used to defeat the whole list: nothing is cut
    # from an end that is a letter, so no reading ever reduced to the listed word. These
    # are here because that is the first thing anybody tries after being refused once.
    "Qwerty123!A",
    "qwerty123!A",
    "Password1!A",
    "Welcome123!z",
    "Iloveyou1!a",
    "Admin@123a",
    "Dhruv@2026x",
    "Ravi@2026x",
    "MyPassw0rd!x",
    "Logins2026!",
    # "sunflower" with an s and a year on it. Listed here rather than in the accepted half
    # on reflection: it is the listed word with trimmings, which is exactly the test.
    "Sunflowers#2026",
]

#: Passwords that must be accepted. This half matters as much as the other: a check that
#: refuses good passwords teaches people to fight the form, and what they produce on the
#: fourth attempt is reliably worse than what they started with. Several of these were
#: refused by an earlier version that searched for listed words *inside* the password.
MUST_ACCEPT = [
    "Str0ngUnique#Phrase",
    "Monsoon-Lychee-42",
    "MyKid2015!",
    "Tr0ub4dor&3",
    "Correct-Horse-Battery",
    "Nilgiri#Tahr7",
    "Zephyr&Quince11",
    "Kaveri#Delta88",
    "Th3-Banyan-Grove",
    "Marigold$Pepper9",
    "Jacaranda!Tide4",
    "Bramble#Lantern2",
    "Quartz-Pelican77",
    "Tamarind7#",
    "Saffron-Kite8!",
    "Ravine-Thistle-Quay-71",
    # Refused by the substring version, for words buried inside longer ones.
    "Beetroot2026!",
    "Examiner7#",
    "Masterclass9!",
    "Accessible7#",
    "Secretariat4!",
    "Dragonfly-9!",
    "Chelsea-Harbour1",
    "Indiana#Jones7",
    "Rootkit99!",
    # Ordinary words that merely *contain* a listed one. Each is at least three characters
    # longer than the word inside it, which is the line between "that word with trimmings"
    # and "a different word".
    "Carpenter42#",
    "Blueberry77$",
    "Akashdeep99!",
    "Ravindra@12",
    "Correct-Horse-Battery9!",
    # The demo accounts, so the seeded world cannot become unsignable-into.
    "Kestrel#Bay74",
    "Marigold$Loom9",
    "Lantern&Fig52",
    "Juniper!Cove8",
    "Bramble@Dune3",
    "Thistle^Reed6",
    "Quartz%Vale41",
    "Kestrel@Fen91",
    "Tamarind7#One",
    "Tamarind7#Two",
    "Nope&Quince11",
    "Wrong@Fen91",
]

HEADER = """/**
 * The common-password list, and the substitutions people use to disguise one.
 *
 * GENERATED FILE — do not edit. Run `python scripts/make_common_passwords.py` in `backend`
 * after changing `app/modules/auth/passwords.py`.
 *
 * The algorithm that uses this lives in `commonPasswords.ts`, hand-written so it can be
 * reviewed like any other code. `commonPasswords.test.ts` checks it against a fixture of
 * answers produced by the Python, so the two cannot quietly disagree.
 */
"""


def render_list() -> str:
    leet = "\n".join(f'  "{key}": "{value}",' for key, value in LEET.items())
    words = "\n".join(f'  "{word}",' for word in sorted(COMMON_PASSWORDS))
    return (
        HEADER + "\n/** Characters people substitute to satisfy a symbol rule without changing"
        " the word. */\nexport const LEET: Record<string, string> = {\n"
        + leet
        + "\n};\n\nexport const COMMON_PASSWORDS: ReadonlySet<string> = new Set([\n"
        + words
        + "\n]);\n"
    )


def render_fixture() -> str:
    cases = [
        {"password": password, "common": is_common(password)}
        for password in [*MUST_REFUSE, *MUST_ACCEPT]
    ]
    wrong = [
        case["password"]
        for case, expected in zip(
            cases, [True] * len(MUST_REFUSE) + [False] * len(MUST_ACCEPT), strict=True
        )
        if case["common"] is not expected
    ]
    if wrong:
        raise SystemExit(
            "The Python check no longer agrees with its own expectations: " + ", ".join(wrong)
        )
    return (
        json.dumps(
            {
                "note": (
                    "Generated by backend/scripts/make_common_passwords.py from the real "
                    "is_common(). The browser implementation must reproduce every answer."
                ),
                "cases": cases,
            },
            indent=2,
        )
        + "\n"
    )


def main() -> None:
    LIST_FILE.write_text(render_list(), encoding="utf-8")
    FIXTURE_FILE.write_text(render_fixture(), encoding="utf-8")
    print(f"wrote {LIST_FILE} ({len(COMMON_PASSWORDS)} words)")
    print(f"wrote {FIXTURE_FILE} ({len(MUST_REFUSE) + len(MUST_ACCEPT)} cases)")


if __name__ == "__main__":
    main()
