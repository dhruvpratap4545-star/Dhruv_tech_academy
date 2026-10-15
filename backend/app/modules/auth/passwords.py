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


#: The list, grouped by word length. The near-match test below only ever needs words
#: within `MAX_RESIDUE` of the form it is looking at, and scanning all 217 for every one of
#: a dozen readings turned a validation into half a millisecond of pure string comparison.
_BY_LENGTH: dict[int, tuple[str, ...]] = {}
for _word in COMMON_PASSWORDS:
    _BY_LENGTH[len(_word)] = (*_BY_LENGTH.get(len(_word), ()), _word)


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


def letters_only(value: str, *, fold: bool) -> str:
    """Just the letters, with the substitutions folded back first or not.

    ``Qwerty123!A`` needs this. It ends in a letter, so nothing is cut from that end, and
    the ``123`` sits in the middle where no edge rule reaches it — every other reading
    keeps those three characters and the result is never exactly ``qwerty``. Dropping the
    digits and symbols outright leaves ``qwertya``, which is one letter away.

    Both foldings, for the usual reason: in ``P@ssw0rd!x`` the ``@`` and the ``0`` are
    letters of the word, and in ``Qwerty123!A`` the ``!`` is punctuation.
    """
    source = "".join(LEET.get(ch, ch) for ch in value.lower()) if fold else value.lower()
    return "".join(ch for ch in source if ch.isalpha())


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

    forms = [
        lowered,
        plain,
        undecorate(value),
        undecorate_digits_only(value),
        letters_only(value, fold=True),
        letters_only(value, fold=False),
    ]
    for base in (value, plain):
        for cut in (_TRAILING_DIGITS.sub("", base), *trimmed_edges(base)):
            if cut and cut != base:
                forms.extend([cut.lower(), undecorate(cut), undecorate_digits_only(cut)])

    # Deduplicated: several of these readings collapse to the same string for most
    # passwords, and the near-match loop below is run once per form.
    return list(dict.fromkeys(form for form in forms if form))


#: A listed word has to be at least this long before a near-match counts. Below it, only
#: an exact match does — "exam" and "ravi" appear inside too many ordinary words.
MIN_WORD_LENGTH = 4

#: ...and the password may add at most this many characters to it. The question being
#: asked is "is this that word with trimmings?", and two characters is where a trimming
#: stops being a trimming.
MAX_RESIDUE = 2


def is_common(value: str) -> bool:
    """True when the password is a known-common one wearing a disguise.

    Two rules, and the balance between them is the whole difficulty.

    **Exact match against every reading.** `candidates` rewrites the password each way a
    reader might take it, so ``P@ssw0rd123`` and ``$h1va@2026`` reduce to ``password`` and
    ``shiva``.

    **Near match, bounded by how much is left over.** Exact matching alone is defeated by a
    single letter: ``Qwerty123!A`` ends in a letter, so nothing is cut from that end, and no
    reading of it is ever exactly ``qwerty``. So a listed word found *inside* a reading also
    counts — but only when the reading is at most `MAX_RESIDUE` characters longer than the
    word. That is the difference between "this is qwerty with a letter stuck on" and "this
    merely contains those six letters somewhere".

    The bound is what an earlier version got wrong. It searched for listed words with a
    ratio test, and refused ``Beetroot2026!`` for containing "root", along with
    ``Examiner7#``, ``Masterclass9!``, ``Dragonfly-9!`` and ``Secretariat4!`` — good
    passwords, rejected after a live checklist had shown all four rules green, with nothing
    to say which part was wrong. A check that refuses good passwords teaches people to
    fight the form, and what they produce on the fourth attempt is reliably worse than what
    they started with. Those five are in the accepted half of the test table for that
    reason, next to the suffixed ones above in the refused half.

    This is a heuristic and it will always be beatable by someone who knows its shape. It
    is here to stop the password people reach for first, not a determined attacker; a real
    strength estimator or a breach-corpus lookup belongs in a later milestone.
    """
    forms = candidates(value)
    if any(form in COMMON_PASSWORDS for form in forms):
        return True

    for form in forms:
        shortest = max(MIN_WORD_LENGTH, len(form) - MAX_RESIDUE)
        for length in range(shortest, len(form) + 1):
            for word in _BY_LENGTH.get(length, ()):
                if word in form:
                    return True
    return False
