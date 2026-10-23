"""Escape-first inline emphasis and bounded paragraph/list formatting for notes."""
import re
from html import escape


def inline(value: str) -> str:
    return re.sub(r"\*\*([^*\n]{1,200})\*\*", r"<b>\1</b>", escape(str(value)))


def paragraphs(value):
    """Reflow saved prose without rewriting its words, facts or code fields."""
    group, words = [], 0
    for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", value.strip()):
        count = len(sentence.split())
        if group and (len(group) >= 3 or words + count > 90):
            yield " ".join(group)
            group, words = [], 0
        group.append(sentence)
        words += count
    if group:
        yield " ".join(group)


def blocks(value: str):
    for line in str(value).splitlines():
        if not line.strip():
            continue
        bullet = re.match(r"^\s*[-•]\s+(.+)", line)
        numbered = re.match(r"^\s*(\d+)[.)]\s+(.+)", line)
        if bullet:
            yield "• ", bullet[1]
        elif numbered:
            yield numbered[1] + ". ", numbered[2]
        else:
            for paragraph in paragraphs(line):
                yield "", paragraph
