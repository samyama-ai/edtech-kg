"""Reading a number a document spells out.

`spelled()` is used inside assertions about documents. What it does with a word
it cannot read decides whether a drifted document produces a legible failure or
an opaque traceback in the test whose subject is legibility.
"""

from __future__ import annotations

import pytest

from tests.spelling import Unspellable, spelled


@pytest.mark.parametrize("word,number", [
    ("four", 4), ("nineteen", 19), ("twenty", 20),
    ("seventy-four", 74), ("ninety-nine", 99),
    ("19", 19), (" Four ", 4),
])
def test_a_document_may_spell_a_number_either_way(word, number):
    assert spelled(word) == number


@pytest.mark.parametrize("word", ["a dozen", "twenty one", "", "   ", None, "eleventy"])
def test_a_word_it_cannot_read_is_an_assertion_not_a_traceback(word):
    """It raised KeyError, which surfaces as an ERROR rather than a failure and
    names the missing dict key instead of the document that needs rewording."""
    with pytest.raises(Unspellable) as raised:
        spelled(word)
    assert "cannot read" in str(raised.value)


def test_the_message_names_the_part_it_could_not_read():
    with pytest.raises(Unspellable, match="dozen"):
        spelled("a dozen")


def test_it_only_goes_one_way():
    """The reverse — predicting how a document will spell a number — was tried
    and wedged a test: with a digits fallback, a document blocking four
    questions demanded the literal "4 questions", so writing "four questions"
    left it failing. The module must not grow that direction back."""
    import tests.spelling as module
    assert not [n for n in vars(module) if "unspell" in n.lower() and n != "Unspellable"]
    assert not hasattr(module, "as_word")
