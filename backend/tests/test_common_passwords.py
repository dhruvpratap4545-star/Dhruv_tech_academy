"""The common-password check, and the guarantee that the browser agrees with it.

The browser has its own copy so somebody typing finds out immediately, rather than after a
round trip. Two copies that disagree produce the worst possible version of that feature: a
live checklist with every box green, and an API that refuses the password anyway. These
tests make that disagreement a build failure instead.

The expectations live in `scripts/make_common_passwords.py` rather than here, because the
same lists are written out as a JSON fixture the browser's own test runs against. One table
of cases, two implementations held to it.
"""

from __future__ import annotations

import json
import pathlib

import pytest

import scripts.make_common_passwords as generator
from app.modules.auth.passwords import COMMON_PASSWORDS, LEET, is_common

FRONTEND = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "features" / "auth"
LIST_FILE = FRONTEND / "commonPasswordList.ts"
FIXTURE_FILE = FRONTEND / "commonPasswords.fixture.json"


@pytest.mark.parametrize("password", generator.MUST_REFUSE)
def test_a_listed_word_in_disguise_is_refused(password: str) -> None:
    """Each of these is a listed word wearing the decoration people add to satisfy a
    character-class rule. All four rules pass on every one of them, which is exactly why
    those rules are not enough on their own."""
    assert is_common(password), f"{password} slipped through"


@pytest.mark.parametrize("password", generator.MUST_ACCEPT)
def test_an_ordinary_password_is_accepted(password: str) -> None:
    """The other half of the bargain.

    A check that refuses good passwords teaches people to fight the form, and what they
    produce on the fourth attempt is reliably worse than what they started with. Several
    of these were refused by an earlier version that searched for listed words *inside*
    the password: "root" in `Beetroot2026!`, "exam" in `Examiner7#`, "dragon" in
    `Dragonfly-9!`.
    """
    assert not is_common(password), f"{password} was refused for no good reason"


def test_a_listed_word_inside_a_longer_one_is_not_a_match() -> None:
    """The specific distinction the substring search got wrong.

    "root" is on the list and "beetroot" is not. Nothing about a password containing those
    four letters says anything about its strength.
    """
    assert is_common("Root@2026")
    assert not is_common("Beetroot2026!")
    assert is_common("Master#99")
    assert not is_common("Masterclass9!")


def test_decoration_is_stripped_from_either_end() -> None:
    """An edge symbol is ambiguous, so every reading is tried.

    In `$h1va@2026` the leading `$` is the `S` of "Shiva" and has to be folded, while the
    trailing `@2026` is padding and has to be cut.
    """
    assert is_common("$h1va@2026")
    assert is_common("2026@Dhruv")
    assert is_common("...Password...")


def test_the_generated_files_are_current() -> None:
    """Running the generator must reproduce exactly what is checked in.

    If this fails, the Python changed and `python scripts/make_common_passwords.py` was not
    run afterwards. It has just been run — review the diff and commit it.
    """
    assert LIST_FILE.exists(), f"{LIST_FILE} is missing"
    assert FIXTURE_FILE.exists(), f"{FIXTURE_FILE} is missing"

    before = (LIST_FILE.read_text(encoding="utf-8"), FIXTURE_FILE.read_text(encoding="utf-8"))
    generator.main()
    after = (LIST_FILE.read_text(encoding="utf-8"), FIXTURE_FILE.read_text(encoding="utf-8"))

    assert after == before, (
        "The browser's copy of the common-password data is out of date. It has just been "
        "regenerated — review the diff and commit it."
    )


def test_the_generated_list_holds_the_same_words_and_substitutions() -> None:
    """Read the file back and check the data, not just that the bytes round-trip.

    The test above would also pass if the generator were broken in the same way as the
    file it writes. This one asserts against the Python values directly.
    """
    source = LIST_FILE.read_text(encoding="utf-8")

    listed = set(
        source.split("new Set([", 1)[1]
        .split("]);", 1)[0]
        .replace('"', "")
        .replace(",", " ")
        .split()
    )
    assert listed == set(COMMON_PASSWORDS)

    for character, letter in LEET.items():
        assert f'"{character}": "{letter}",' in source


def test_the_fixture_records_what_python_actually_answers() -> None:
    """The fixture is the contract the browser's test is held to, so it has to be true.

    Generated from `is_common` rather than typed out, but a fixture that was stale in both
    directions at once would still pass `test_the_generated_files_are_current`.
    """
    cases = json.loads(FIXTURE_FILE.read_text(encoding="utf-8"))["cases"]
    assert len(cases) == len(generator.MUST_REFUSE) + len(generator.MUST_ACCEPT)
    for case in cases:
        assert is_common(case["password"]) is case["common"], case["password"]
