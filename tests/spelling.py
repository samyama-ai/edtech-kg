"""Reading a number a document spells out.

One direction only, deliberately. The reverse — predicting how a document will
spell a number — was tried and can wedge a test: with a digits fallback, a
document blocking four questions makes the check demand the literal `"4
questions"`, so writing "four questions" (the natural fix, and the register both
documents use) leaves the test failing. That is a stuck test in the files whose
whole job is catching drift.

So: convert the document's word to an int and compare ints. Never go the other
way.
"""

WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
         "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
         "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
         "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
         "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
         "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}


class Unspellable(AssertionError):
    """A word this cannot read as a number.

    An AssertionError, not a KeyError. The callers use `spelled()` inside
    assertions about a document, and a document that says "a dozen" or "twenty
    one" (unhyphenated) is a document that needs rewording — a legible failure,
    not a traceback in a test whose whole subject is legibility.
    """


def spelled(word: str) -> int:
    """`"seventy-four"` -> `74`. Digits pass through, so a document may write
    either and the check still reads it."""
    word = (word or "").strip().lower()
    if word.isdigit():
        return int(word)
    parts = word.split("-")
    unknown = [p for p in parts if p not in WORDS]
    if not word or unknown:
        raise Unspellable(
            f"cannot read {word!r} as a number — {unknown or 'it is empty'}. "
            f"Either the document should spell it with a word this knows, or "
            f"the word belongs in WORDS.")
    return sum(WORDS[p] for p in parts)
