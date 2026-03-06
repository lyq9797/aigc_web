import re
from typing import Any


SENT_SPLIT_RE = re.compile(r"(?<=[。！？.!?])\s+")
WORD_RE = re.compile(r"\S+")


def split_sentences(text: str) -> list[str]:
    """将文本按句子进行拆分。

    支持中文和英文的句号、感叹号、问号作为句子分隔符，
    分隔符后需要有空白字符才会触发拆分。
    """
    # 处理 None 或纯空白的情况
    if not text or not text.strip():
        return []

    text = text.strip()
    chunks = SENT_SPLIT_RE.split(text)
    merged = [c.strip() for c in chunks if c.strip()]
    if merged:
        return merged

    # 回退：按换行拆分
    return [line.strip() for line in text.splitlines() if line.strip()] or [text]


def tokenize_with_spans(text: str) -> list[dict[str, Any]]:
    """将文本分词，并返回每个词的字符位置信息。

    返回的每个 dict 包含：
      - index: 词的序号（从 0 开始）
      - token: 词的文本内容
      - start: 词在原文中的起始字符位置
      - end: 词在原文中的结束字符位置
    """
    if not text:
        return []

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