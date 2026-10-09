"""The common-password check, and the guarantee that the browser agrees with it.

The browser has its own copy so somebody typing finds out immediately, rather than after a
round trip. Two copies that disagree produce the worst possible version of that feature: a
live checklist with every box green, and an API that refuses the password anyway. These
tests make that disagreement a build failure instead.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

from app.modules.auth.passwords import (
    COMMON_PASSWORDS,
    LEET,
    MIN_COVERAGE,
    MIN_WORD_LENGTH,
    is_common,
)

GENERATOR = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "make_common_passwords.py"
BROWSER_COPY = (
    pathlib.Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "features"
    / "auth"
    / "commonPasswords.ts"
)


# Each of these is a real password shape: a listed word with decoration bolted on to get
# past a character-class rule. Every one of them satisfies length, letter, digit and
# symbol, which is exactly why the four rules are not enough on their own.
@pytest.mark.parametrize(
    "password",
    [
        "Password123!",
        "P@ssw0rd123",
        "passw0rd00",
        "Dhruv@2026",
        "Dhruv!2026",
        "Academy@123",
        "Student@2026",
        "Sachin$123",
        "Krishna@108",
        "Jaishreeram@1",
        "$h1va@2026",
        "Ravi@2026",
        "#Pooja1234",
        "mumbai@123",
        "qwerty99",
        "zxcvbnm1",
        "Qw3rty!2026",
        "l3tm31n!",
        "Adm1n@123",
        "C0mput3r#1",
        "Cr1cket!99",
        "iloveyou143",
    ],
)
def test_a_listed_word_in_disguise_is_refused(password: str) -> None:
    assert is_common(password), f"{password} slipped through"


# The other half of the bargain. A check that refuses too much teaches people to fight the
# form, and what they produce after four rejections is reliably worse than what they
# started with.
@pytest.mark.parametrize(
    "password",
    [
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
    ],
)
def test_an_ordinary_password_is_accepted(password: str) -> None:
    assert not is_common(password), f"{password} was refused for no good reason"


def test_a_common_word_buried_in_a_long_passphrase_is_fine() -> None:
    """Coverage, not mere containment.

    "ravi" appearing somewhere inside twenty-odd characters says nothing about the
    passphrase's strength. The rule is whether the password *is* a listed word with
    trimmings, which is what the coverage threshold measures.
    """
    assert is_common("Ravi@2026")
    assert not is_common("Ravine-Thistle-Quay-71")


def test_the_browser_copy_is_generated_and_current() -> None:
    """Running the generator must produce exactly the file that is checked in.

    If this fails, the Python changed and `python scripts/make_common_passwords.py` was not
    run afterwards. Run it, and commit the result.
    """
    assert BROWSER_COPY.exists(), f"{BROWSER_COPY} is missing"
    before = BROWSER_COPY.read_text(encoding="utf-8")

    result = subprocess.run(  # noqa: S603 - two constants, both from this repository
        [sys.executable, str(GENERATOR)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr

    after = BROWSER_COPY.read_text(encoding="utf-8")
    assert after == before, (
        "The browser's copy of the common-password list is out of date. It has just been "
        "regenerated — review the diff and commit it."
    )


def test_the_browser_copy_holds_the_same_words_and_thresholds() -> None:
    """Read the generated file back and check the data itself, not just the bytes.

    The test above would also pass if the generator were broken in the same way as the
    file it writes. This one asserts against the Python values directly.
    """
    source = BROWSER_COPY.read_text(encoding="utf-8")

    listed = set(
        source.split("new Set([", 1)[1]
        .split("]);", 1)[0]
        .replace('"', "")
        .replace(",", " ")
        .split()
    )
    assert listed == set(COMMON_PASSWORDS)

    assert f"MIN_WORD_LENGTH = {MIN_WORD_LENGTH};" in source
    assert f"MIN_COVERAGE = {MIN_COVERAGE};" in source
    for character, letter in LEET.items():
        assert f'"{character}": "{letter}",' in source
