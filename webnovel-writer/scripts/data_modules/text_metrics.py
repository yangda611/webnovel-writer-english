"""Shared text measurement policy.

``zh`` preserves the legacy ``len(text.strip())`` character count, including
internal whitespace and punctuation. ``en`` counts Unicode letter/number runs
(combining marks belong to their preceding letter). Internal straight/curly
apostrophes and hyphens join a word; dotted initialisms such as U.S.A. are one
word. Standalone numbers count, decimal/grouping punctuation between digits
joins one number, and a slash separates numbers. Underscores and em dashes
separate words. No dictionary or locale-dependent segmentation is used.

``count_text`` measures raw text: heading text counts, Markdown punctuation
does not form English words. Chapter consumers all use ``count_chapter_text``
instead, excluding ATX heading lines, triple-backtick code blocks and ``---`` markers
before applying the same policy (the existing Chinese chapter convention).
The historical field names ``word_count``/``total_words`` remain; their unit
is always carried separately as ``characters`` or ``words``.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any


_INITIALISM = re.compile(r"(?<!\w)(?:[^\W\d_]\.){2,}", re.UNICODE)
_JOINERS = "'’\u02bc-\u2010\u2011"


def count_text(text: str, body_language: str = "zh") -> int:
    """Count characters or Unicode words according to the policy above."""
    if body_language == "zh":
        return len(text.strip())
    if body_language != "en":
        raise ValueError(f"Unsupported body_language: {body_language!r}")

    text = unicodedata.normalize("NFC", text)
    text = _INITIALISM.sub(lambda match: match.group().replace(".", ""), text)
    count = 0
    in_word = False
    for index, char in enumerate(text):
        category = unicodedata.category(char)[0]
        if category in {"L", "N"}:
            if not in_word:
                count += 1
            in_word = True
        elif category == "M" and in_word:
            continue
        elif (
            in_word
            and char in _JOINERS
            and index + 1 < len(text)
            and unicodedata.category(text[index + 1])[0] in {"L", "N"}
        ):
            continue
        elif (
            in_word
            and char in ".,"
            and text[index - 1].isdecimal()
            and index + 1 < len(text)
            and text[index + 1].isdecimal()
        ):
            continue
        else:
            in_word = False
    return count


def count_chapter_text(content: str, body_language: str = "zh") -> int:
    """Measure narrative with the shared legacy chapter Markdown filtering."""
    text = re.sub(r"```[\s\S]*?```", "", content)
    text = re.sub(r"^#+ .*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"---", "", text)
    return count_text(text, body_language)


def chapter_measurement(
    project_root: Path,
    chapter: int,
    *,
    state: dict[str, Any] | None = None,
    incoming_count: int = 0,
) -> dict[str, Any]:
    """Read authoritative chapter text and attach the profile's explicit unit.

    Only pure legacy projects retain positive imported metadata counts.
    Explicit profile projects require a readable manuscript, including on replay;
    missing files must remain a visible projection error rather than stale totals.
    """
    from chapter_paths import find_chapter_file

    from .writing_profile import load_writing_profile

    root = Path(project_root)
    profile = load_writing_profile(root, state=state)
    explicit = (root / ".story-system" / "WRITING_PROFILE.json").is_file()
    if not explicit and incoming_count > 0:
        count = incoming_count
    else:
        path = find_chapter_file(root, chapter)
        if path is None:
            if explicit:
                raise FileNotFoundError(f"第{chapter}章正文不存在，无法计算{profile.chapter_unit}")
            count = 0
        else:
            try:
                count = count_chapter_text(path.read_text(encoding="utf-8"), profile.body_language)
            except OSError:
                if explicit:
                    raise
                count = 0
    return {"word_count": count, "count_unit": profile.chapter_unit, "body_language": profile.body_language}
