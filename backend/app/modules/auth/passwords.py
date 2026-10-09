"""The "that password is too common" check.

Four structural rules — length, a letter, a digit, a symbol — stop almost nothing on their
own, because the passwords people actually choose satisfy all four. `Password123!` is
twelve characters with a letter, a digit and a symbol, and it is among the most guessed
strings in the world. So the rules are paired with a list, and the list is only useful if
it sees through the decoration people add to get past the rules.

The password is not compared to the list directly. It is first rewritten every way a
reader might reasonably read it, and the list is consulted for each:

* **Undecorated.** Lower-cased, with the usual character substitutions folded back to
  letters (``@`` to ``a``, ``0`` to ``o``, ``$`` to ``s``), then everything that is not a
  letter or digit removed. ``P@ssw0rd`` becomes ``password``.
* **With the symbols dropped rather than folded.** ``!`` is an ``i`` in ``l3tm31n!`` and
  an exclamation mark in ``Password!``, and nothing in the string says which, so both
  readings are produced.
* **With the decoration cut off the edges** — leading, trailing, and both. The same
  ambiguity again: in ``$h1va@2026`` the leading ``$`` is the ``S`` of "Shiva" and must be
  folded, while the trailing ``@2026`` is padding and must be cut.

A password is refused only when one of those readings *is* a listed word. There is no
substring search. An earlier version had one, and it refused ``Beetroot2026!`` because
"root" is on the list, along with ``Examiner7#``, ``Masterclass9!`` and
``Dragonfly-9!`` — good passwords, rejected with a message that gave the person no way to
work out which part was wrong, after a live checklist had shown every rule satisfied.

The same readings are produced in the browser, in
``frontend/src/features/auth/commonPasswords.ts``, which is generated from this file by
``scripts/make_common_passwords.py``. ``tests/test_common_passwords.py`` fails the build if
the two drift apart, because a checklist that goes all green and is then refused by the API
is worse than no checklist at all.
"""

from __future__ import annotations

import re

#: Characters people substitute to satisfy a symbol rule without changing the word.
LEET: dict[str, str] = {
    "@": "a",
    "4": "a",
    "8": "b",
    "(": "c",
    "3": "e",
    "6": "g",
    "9": "g",
    "1": "i",
    "!": "i",
    "|": "i",
    "0": "o",
    "5": "s",
    "$": "s",
    "7": "t",
    "+": "t",
    "2": "z",
}

_TRAILING_DIGITS = re.compile(r"\d+$")

# Everything here is either a top-ranked password in breach corpora, a keyboard walk, or a
# word this product invites people to reach for — "dhruv", "academy", "student", "college".
COMMON_PASSWORDS: frozenset[str] = frozenset(
    {
        # the perennial top of every list
        "password",
        "passwort",
        "passord",
        "contrasena",
        "qwerty",
        "qwertyuiop",
        "qwertz",
        "azerty",
        "asdfgh",
        "asdfghjkl",
        "zxcvbn",
        "zxcvbnm",
        "qazwsx",
        "qweasdzxc",
        "iqzwderf",
        "iqazzwsx",
        "abcdef",
        "abcdefg",
        "abcdefgh",
        # pure digits and runs
        "123456",
        "1234567",
        "12345678",
        "123456789",
        "1234567890",
        "987654321",
        "11111111",
        "00000000",
        "123123123",
        "112233",
        "121212",
        "123321",
        "654321",
        "666666",
        "696969",
        "777777",
        "888888",
        "999999",
        # words people pick
        "iloveyou",
        "princess",
        "sunshine",
        "superman",
        "batman",
        "spiderman",
        "pokemon",
        "football",
        "baseball",
        "basketball",
        "cricket",
        "soccer",
        "michael",
        "jennifer",
        "jessica",
        "daniel",
        "nicole",
        "hunter",
        "shadow",
        "master",
        "monkey",
        "dragon",
        "freedom",
        "whatever",
        "trustno",
        "letmein",
        "welcome",
        "login",
        "secret",
        "ninja",
        "cheese",
        "buster",
        "butterfly",
        "chocolate",
        "computer",
        "internet",
        "liverpool",
        "arsenal",
        "chelsea",
        "barcelona",
        "realmadrid",
        "manchester",
        "starwars",
        "flower",
        "sunflower",
        "rainbow",
        "jordan",
        "harley",
        "ranger",
        "tigger",
        "thomas",
        "robert",
        "matthew",
        "andrew",
        "joshua",
        "amanda",
        "ashley",
        "samantha",
        "anthony",
        "charlie",
        "summer",
        "winter",
        "autumn",
        "forever",
        "angel",
        "babygirl",
        "lovely",
        "sweetie",
        "darling",
        "mother",
        "father",
        "family",
        # administrative and default-ish
        "admin",
        "administrator",
        "adminadmin",
        "root",
        "rootroot",
        "toor",
        "guest",
        "default",
        "changeme",
        "temporary",
        "temppass",
        "newpass",
        "mypassword",
        "yourpassword",
        "passpass",
        "access",
        "manager",
        "service",
        "support",
        "testtest",
        "testing",
        "demodemo",
        "sample",
        "sandbox",
        "example",
        "trustme",
        # Indian-context favourites
        "india",
        "indian",
        "bharat",
        "mumbai",
        "delhi",
        "chennai",
        "kolkata",
        "bangalore",
        "hyderabad",
        "krishna",
        "ganesh",
        "ganesha",
        "shiva",
        "saibaba",
        "hanuman",
        "jaishreeram",
        "bajrangbali",
        "radhekrishna",
        "omnamahshivaya",
        "sachin",
        "dhoni",
        "virat",
        "kohli",
        "rohit",
        "tendulkar",
        "salman",
        "shahrukh",
        "bollywood",
        "namaste",
        "chaiwala",
        "dosti",
        "pyaar",
        "mohabbat",
        "dilwale",
        "aditya",
        "akash",
        "ananya",
        "ankit",
        "arjun",
        "deepak",
        "kavita",
        "manish",
        "neha",
        "pooja",
        "prakash",
        "priya",
        "rahul",
        "rajesh",
        "ravi",
        "rohan",
        "sandeep",
        "sanjay",
        "shivam",
        "sneha",
        "sunita",
        "suresh",
        "vijay",
        "vikram",
        "vishal",
        # this product's own words — the first thing anyone types
        "dhruv",
        "dhruvacademy",
        "dhruvonline",
        "dhruvonlineacademy",
        "academy",
        "onlineacademy",
        "student",
        "students",
        "teacher",
        "teachers",
        "faculty",
        "college",
        "school",
        "institute",
        "university",
        "classroom",
        "education",
        "learning",
        "exam",
        "result",
        "library",
        "wallet",
        "coaching",
    }
)


def undecorate(value: str) -> str:
    """Fold every substitution back to a letter, then keep only letters and digits."""
    folded = "".join(LEET.get(ch, ch) for ch in value.lower())
    return "".join(ch for ch in folded if ch.isalnum())


def undecorate_digits_only(value: str) -> str:
    """Fold the digit substitutions, but throw the symbols away instead of folding them.

    ``l3tm31n!`` needs this. Folding everything turns the final ``!`` into an ``i`` and
    produces ``letmeini``; folding only the digits and discarding the punctuation gives
    ``letmein``. Both readings are plausible — ``!`` really is used for ``i`` mid-word, and
    it is also just an exclamation mark on the end — so both are tried.
    """
    folded = "".join(LEET.get(ch, ch) if ch.isdigit() else ch for ch in value.lower())
    return "".join(ch for ch in folded if ch.isalnum())


#: Runs of digits and symbols at the edges — the decoration people add to get past a
#: character-class rule, wrapped around the word they actually chose.
_LEADING_DECORATION = re.compile(r"^[^A-Za-z]+")
_TRAILING_DECORATION = re.compile(r"[^A-Za-z]+$")


def trimmed_edges(value: str) -> list[str]:
    """``value`` with its leading decoration gone, its trailing decoration gone, and both.

    All three, because an edge symbol is ambiguous and only the reader knows which it is.
    In ``$h1va@2026`` the leading ``$`` is the ``S`` of "Shiva" and has to be folded, while
    the trailing ``@2026`` is decoration and has to be cut. Cutting both ends gives
    ``h1va`` — "hiva", which is nothing. Cutting only the trailing end leaves ``$h1va``,
    which folds to exactly ``shiva``.

    ``2026@Dhruv`` needs the mirror image, and ``Beetroot2026!`` needs the trailing cut so
    that it ends up as "beetroot" and is correctly left alone.
    """
    return [
        _TRAILING_DECORATION.sub("", value),
        _LEADING_DECORATION.sub("", value),
        _LEADING_DECORATION.sub("", _TRAILING_DECORATION.sub("", value)),
    ]


def candidates(value: str) -> list[str]:
    """Every reading of ``value`` worth checking.

    There is no single correct normalisation, because the same character means different
    things in different passwords. ``!`` is an ``i`` in ``l3tm31n!`` and an exclamation
    mark in ``Password!``. ``0`` is an ``o`` in ``passw0rd`` and a zero in ``Student2026``.
    Rather than guess, every plausible reading is produced and the password is refused if
    any one of them is exactly a listed word.
    """
    lowered = value.lower()
    plain = "".join(ch for ch in lowered if ch.isalnum())

    forms = [lowered, plain, undecorate(value), undecorate_digits_only(value)]
    for base in (value, plain):
        for cut in (_TRAILING_DIGITS.sub("", base), *trimmed_edges(base)):
            if cut and cut != base:
                forms.extend([cut.lower(), undecorate(cut), undecorate_digits_only(cut)])
    return [form for form in forms if form]


def is_common(value: str) -> bool:
    """True when the password is a known-common one wearing a disguise.

    Exact matching, against every reading of the password that `candidates` produces. An
    earlier version also searched each reading for a listed word *inside* it, on the
    reasoning that ``$h1va@2026`` never normalises to exactly ``shiva``. It does now —
    `undecorate_edges` cuts the decoration off both ends first — and the substring search
    turned out to cost far more than it bought.

    What it cost: ``Beetroot2026!`` was refused because "root" is in the list, and so were
    ``Examiner7#``, ``Masterclass9!``, ``Dragonfly-9!`` and ``Secretariat4!``. Every one of
    those is a good password, and the person typing one was told only "that password is too
    common" with no way to work out which part of it was the problem — after a live
    checklist had shown all four rules green. A check that refuses good passwords teaches
    people to fight the form, and what they produce on the fourth attempt is reliably worse
    than what they started with.
    """
    return any(form in COMMON_PASSWORDS for form in candidates(value))
