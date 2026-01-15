import re
from typing import Any


SENT_SPLIT_RE = re.compile(r"(?<=[。！？.!?])\s+")
WORD_RE = re.compile(r"\S+")


def split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks = SENT_SPLIT_RE.split(text)
    merged = [c.strip() for c in chunks if c.strip()]
    if merged:
        return merged

    return [line.strip() for line in text.splitlines() if line.strip()] or [text]


def tokenize_with_spans(text: str) -> list[dict[str, Any]]:
    tokens = []
    for idx, m in enumerate(WORD_RE.finditer(text)):
        tokens.append(
            {
                "index": idx,
                "token": m.group(0),
                "start": m.start(),
                "end": m.end(),
            }
        )
    return tokens
