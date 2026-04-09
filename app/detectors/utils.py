import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---- 常量 ----
MIN_SENTENCE_LENGTH = 1
SENT_SPLIT_RE = re.compile(r"(?<=[。！？.!?；;])\s+")
WORD_RE = re.compile(r"\S+")


class TextProcessor:
    """文本处理器，提供句子拆分和分词功能。"""

    def __init__(self, min_sentence_length: int = MIN_SENTENCE_LENGTH):
        self.min_sentence_length = min_sentence_length

    def split_sentences(self, text: str) -> list[str]:
        """将文本按句子进行拆分。

        支持中文和英文的句号、感叹号、问号、分号作为句子分隔符。
        如果无法按标点拆分，则按换行拆分。
        """
        if not isinstance(text, str) or not text.strip():
            logger.debug("split_sentences 收到空输入，返回空列表")
            return []

        text = text.strip()
        chunks = SENT_SPLIT_RE.split(text)

        merged = [
            c.strip() for c in chunks
            if c.strip() and len(c.strip()) >= self.min_sentence_length
        ]

        if len(merged) <= 1:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if len(lines) > 1:
                logger.debug("回退到按换行拆分，得到 %d 个句子", len(lines))
                return lines

        if merged:
            logger.debug("按标点拆分得到 %d 个句子", len(merged))
            return merged

        return [text]

    def tokenize_with_spans(self, text: str) -> list[dict[str, Any]]:
        """将文本分词，并返回每个词的位置信息。

        返回的每个 dict 包含：index, token, start, end, length
        """
        if not isinstance(text, str) or not text:
            return []

        tokens = []
        for idx, m in enumerate(WORD_RE.finditer(text)):
            word = m.group(0)
            tokens.append(
                {
                    "index": idx,
                    "token": word,
                    "start": m.start(),
                    "end": m.end(),
                    "length": len(word),  # 新增字段
                }
            )

        logger.debug("共切分出 %d 个 token", len(tokens))
        return tokens

    def batch_split_sentences(self, texts: list[str]) -> list[list[str]]:
        """批量拆分多个文本的句子。"""
        results = []
        for i, text in enumerate(texts):
            sentences = self.split_sentences(text)
            logger.debug("第 %d 段文本拆分为 %d 个句子", i, len(sentences))
            results.append(sentences)
        return results

    def get_sentence_count(self, text: str) -> int:
        """返回文本的句子数量。"""
        return len(self.split_sentences(text))


# ---- 模块级便捷函数（使用默认配置） ----

_default_processor = TextProcessor()

split_sentences = _default_processor.split_sentences
tokenize_with_spans = _default_processor.tokenize_with_spans
get_sentence_count = _default_processor.get_sentence_count