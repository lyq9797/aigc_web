import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---- 常量 ----
MIN_SENTENCE_LENGTH = 1          # 最短句子长度（过滤掉无意义片段）
SENT_SPLIT_RE = re.compile(r"(?<=[。！？.!?；;])\s+")
WORD_RE = re.compile(r"\S+")


def split_sentences(text: str) -> list[str]:
    """将文本按句子进行拆分。

    支持中文和英文的句号、感叹号、问号、分号作为句子分隔符。
    如果无法按标点拆分，则按换行拆分。
    """
    if not isinstance(text, str) or not text.strip():
        logger.debug("split_sentences 收到空输入，返回空列表")
        return []

    text = text.strip()
    chunks = SENT_SPLIT_RE.split(text)

    # 过滤过短的片段
    merged = [
        c.strip() for c in chunks
        if c.strip() and len(c.strip()) >= MIN_SENTENCE_LENGTH
    ]

    # 如果拆分结果只有一段，尝试按换行拆分
    if len(merged) <= 1:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) > 1:
            logger.debug("回退到按换行拆分，得到 %d 个句子", len(lines))
            return lines

    if merged:
        logger.debug("按标点拆分得到 %d 个句子", len(merged))
        return merged

    return [text]


def tokenize_with_spans(text: str) -> list[dict[str, Any]]:
    """将文本分词，并返回每个词的字符位置信息。"""
    if not isinstance(text, str) or not text:
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

    logger.debug("tokenize_with_spans 共切分出 %d 个 token", len(tokens))
    return tokens


def get_sentence_count(text: str) -> int:
    """返回文本的句子数量（便捷函数）。"""
    return len(split_sentences(text))