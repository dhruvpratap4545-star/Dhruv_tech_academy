"""The "that password is too common" check.

Four structural rules — length, a letter, a digit, a symbol — stop almost nothing on their
own, because the passwords people actually choose satisfy all four. `Password123!` is
twelve characters with a letter, a digit and a symbol, and it is among the most guessed
strings in the world. So the rules are paired with a list, and the list is only useful if
it sees through the decoration people add to get past the rules.

Two steps, in order:

1. **Undecorate.** Lower-case, fold the usual character substitutions back to letters
   (``@`` to ``a``, ``0`` to ``o``, ``$`` to ``s``, and so on), then drop everything that
   is not a letter or a digit. ``P@ssw0rd!`` and ``p a s s w o r d`` both become
   ``password``.
2. **Strip the trailing run of digits** and try again, so ``password2026``, ``qwerty99``
   and ``iloveyou143`` are recognised as what they are. Only trailing digits, and only
   when something is left — ``123456`` still has to be caught by step 1.

The same two steps run in the browser, in ``frontend/src/features/auth/commonPasswords.ts``.
``tests/test_common_passwords.py`` reads that file and fails if the two drift apart, because
a checklist that ticks every box and is then refused by the API is worse than no checklist.
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


#: A matched word must be at least this long, or "ravi" would fire inside "travinder".
MIN_WORD_LENGTH = 4

#: ...and must account for at least this much of the password, or one common word buried
#: in a genuinely long passphrase would be refused for no reason.
MIN_COVERAGE = 0.5


def candidates(value: str) -> list[str]:
    """Every reading of ``value`` worth checking.

    There is no single correct normalisation, because the same character means different
    things in different passwords. ``!`` is an ``i`` in ``l3tm31n!`` and an exclamation
    mark in ``Password!``. ``0`` is an ``o`` in ``passw0rd`` and a zero in ``Student2026``.
    Rather than guess, every plausible reading is produced and the password is refused if
    *any* of them is a known-common one.
    """
    lowered = value.lower()
    plain = "".join(ch for ch in lowered if ch.isalnum())

    forms = [lowered, plain, undecorate(value), undecorate_digits_only(value)]
    for base in (value, plain):
        stripped = _TRAILING_DIGITS.sub("", base)
        if stripped and stripped != base:
            forms.append(stripped.lower())
            forms.append(undecorate(stripped))
            forms.append(undecorate_digits_only(stripped))
    return [form for form in forms if form]


def is_common(value: str) -> bool:
    """True when the password is a known-common one wearing a disguise.

    Exact matching alone is not enough. ``$h1va@2026`` is "Shiva" with a dollar sign, a
    one, and this year stuck on the end; no normalisation turns it into exactly ``shiva``,
    because the decoration is on both sides of the word. So each reading is also searched
    for a listed word *inside* it.

    Two conditions keep that from refusing everything. The word has to be at least
    ``MIN_WORD_LENGTH`` characters, so short names do not fire inside longer ones, and it
    has to make up at least ``MIN_COVERAGE`` of what was typed — the test of whether the
    password *is* that word with trimmings, or merely contains it somewhere.
    ``Ravi@2026`` reads as "ravi" plus decoration and is refused; a twenty-character
    passphrase that happens to contain "ravi" is not.
    """
    forms = candidates(value)
    if any(form in COMMON_PASSWORDS for form in forms):
        return True

    for form in forms:
        threshold = len(form) * MIN_COVERAGE
        for word in COMMON_PASSWORDS:
            if len(word) >= MIN_WORD_LENGTH and len(word) >= threshold and word in form:
                return True
    return False
