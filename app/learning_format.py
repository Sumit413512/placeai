"""Escape-first inline emphasis and bounded paragraph/list formatting for notes."""
import re
from html import escape


def inline(value: str) -> str:
    return re.sub(r"\*\*([^*\n]{1,200})\*\*", r"<b>\1</b>", escape(str(value)))


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
            yield "", line.strip()
