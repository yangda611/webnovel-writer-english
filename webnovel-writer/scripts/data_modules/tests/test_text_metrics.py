"""The public counting policy is shared by all chapter read models."""

import pytest

from data_modules.text_metrics import count_chapter_text, count_text


SAMPLE = "The old bridge crossed the river beneath a pale sky."


def test_user_english_example_is_ten_words():
    assert len(SAMPLE) == 52
    assert count_text(SAMPLE, "en") == 10


@pytest.mark.parametrize("text", ["  中文，保留标点。\n", "a b\n中文", "", " \n "])
def test_chinese_retains_trimmed_character_count(text):
    assert count_text(text) == len(text.strip())


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Don't stop; it’s a well-known, state‑of‑the‑art path.", 7),
        ("Dr. O’Neil met Éowyn and Jose\u0301 in the U.S.A.", 9),
        ("Level 42 costs 1,000.50 coins; 3/5 remain in 2026-11-03.", 10),
        ("# Chapter One\nThe bridge.", 4),
        ("foo_bar em—dash 中文。", 5),
        ("a\u035c b", 2),
        ("!!! ... -- \n", 0),
    ],
)
def test_unicode_english_token_policy(text, expected):
    assert count_text(text, "en") == expected


@pytest.mark.parametrize("language, expected", [("en", 10), ("zh", 52)])
def test_chapter_markup_is_removed_consistently(language, expected):
    content = f"# Chapter One\n\n{SAMPLE}\n\n---\n```text\nnot narrative\n```\n"
    assert count_chapter_text(content, language) == expected


def test_unsupported_language_is_explicit():
    with pytest.raises(ValueError, match="body_language"):
        count_text("bonjour", "fr")
