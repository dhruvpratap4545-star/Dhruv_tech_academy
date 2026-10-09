/**
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

/** Characters people substitute to satisfy a symbol rule without changing the word. */
export const LEET: Record<string, string> = {
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
};

/** A matched word must be at least this long, or "ravi" would fire inside "travinder". */
export const MIN_WORD_LENGTH = 4;

/**
 * ...and must account for at least this much of the password, or one common word buried in
 * a genuinely long passphrase would be refused for no reason.
 */
export const MIN_COVERAGE = 0.5;

export const COMMON_PASSWORDS: ReadonlySet<string> = new Set([
  "00000000",
  "11111111",
  "112233",
  "121212",
  "123123123",
  "123321",
  "123456",
  "1234567",
  "12345678",
  "123456789",
  "1234567890",
  "654321",
  "666666",
  "696969",
  "777777",
  "888888",
  "987654321",
  "999999",
  "abcdef",
  "abcdefg",
  "abcdefgh",
  "academy",
  "access",
  "aditya",
  "admin",
  "adminadmin",
  "administrator",
  "akash",
  "amanda",
  "ananya",
  "andrew",
  "angel",
  "ankit",
  "anthony",
  "arjun",
  "arsenal",
  "asdfgh",
  "asdfghjkl",
  "ashley",
  "autumn",
  "azerty",
  "babygirl",
  "bajrangbali",
  "bangalore",
  "barcelona",
  "baseball",
  "basketball",
  "batman",
  "bharat",
  "bollywood",
  "buster",
  "butterfly",
  "chaiwala",
  "changeme",
  "charlie",
  "cheese",
  "chelsea",
  "chennai",
  "chocolate",
  "classroom",
  "coaching",
  "college",
  "computer",
  "contrasena",
  "cricket",
  "daniel",
  "darling",
  "deepak",
  "default",
  "delhi",
  "demodemo",
  "dhoni",
  "dhruv",
  "dhruvacademy",
  "dhruvonline",
  "dhruvonlineacademy",
  "dilwale",
  "dosti",
  "dragon",
  "education",
  "exam",
  "example",
  "faculty",
  "family",
  "father",
  "flower",
  "football",
  "forever",
  "freedom",
  "ganesh",
  "ganesha",
  "guest",
  "hanuman",
  "harley",
  "hunter",
  "hyderabad",
  "iloveyou",
  "india",
  "indian",
  "institute",
  "internet",
  "iqazzwsx",
  "iqzwderf",
  "jaishreeram",
  "jennifer",
  "jessica",
  "jordan",
  "joshua",
  "kavita",
  "kohli",
  "kolkata",
  "krishna",
  "learning",
  "letmein",
  "library",
  "liverpool",
  "login",
  "lovely",
  "manager",
  "manchester",
  "manish",
  "master",
  "matthew",
  "michael",
  "mohabbat",
  "monkey",
  "mother",
  "mumbai",
  "mypassword",
  "namaste",
  "neha",
  "newpass",
  "nicole",
  "ninja",
  "omnamahshivaya",
  "onlineacademy",
  "passord",
  "passpass",
  "password",
  "passwort",
  "pokemon",
  "pooja",
  "prakash",
  "princess",
  "priya",
  "pyaar",
  "qazwsx",
  "qweasdzxc",
  "qwerty",
  "qwertyuiop",
  "qwertz",
  "radhekrishna",
  "rahul",
  "rainbow",
  "rajesh",
  "ranger",
  "ravi",
  "realmadrid",
  "result",
  "robert",
  "rohan",
  "rohit",
  "root",
  "rootroot",
  "sachin",
  "saibaba",
  "salman",
  "samantha",
  "sample",
  "sandbox",
  "sandeep",
  "sanjay",
  "school",
  "secret",
  "service",
  "shadow",
  "shahrukh",
  "shiva",
  "shivam",
  "sneha",
  "soccer",
  "spiderman",
  "starwars",
  "student",
  "students",
  "summer",
  "sunflower",
  "sunita",
  "sunshine",
  "superman",
  "support",
  "suresh",
  "sweetie",
  "teacher",
  "teachers",
  "temporary",
  "temppass",
  "tendulkar",
  "testing",
  "testtest",
  "thomas",
  "tigger",
  "toor",
  "trustme",
  "trustno",
  "university",
  "vijay",
  "vikram",
  "virat",
  "vishal",
  "wallet",
  "welcome",
  "whatever",
  "winter",
  "yourpassword",
  "zxcvbn",
  "zxcvbnm",
]);

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
