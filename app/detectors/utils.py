"""
detector.utils
==============

文本预处理工具模块，提供句子拆分和分词功能。

主要功能:
    - ``TextProcessor.split_sentences``: 按标点/换行拆分句子
    - ``TextProcessor.tokenize_with_spans``: 按空白分词并记录字符偏移
    - 支持批量处理和便捷统计接口

典型用法::

    from app.detector.utils import TextProcessor

    processor = TextProcessor()
    sentences = processor.split_sentences("你好世界。这是测试！")
    tokens = processor.tokenize_with_spans(sentences[0])
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Sequence

__all__ = [
    "Token",
    "TextProcessor",
    "split_sentences",
    "tokenize_with_spans",
    "get_sentence_count",
]

logger = logging.getLogger(__name__)

# ============================================================
# 正则常量
# ============================================================
# 匹配句子结尾标点（中英文句号、感叹号、问号、分号）后的空白
_SENT_SPLIT_RE = re.compile(r"(?<=[。！？.!?；;])\s+")
# 匹配非空白字符序列（即"词"）
_WORD_RE = re.compile(r"\S+")

# 默认最短句子长度，低于该长度的拆分片段将被过滤
_DEFAULT_MIN_SENTENCE_LENGTH = 1


# ============================================================
# 数据结构
# ============================================================
@dataclass(frozen=True)
class Token:
    """表示一个分词结果。

    Attributes:
        index: 词在文本中的序号（从 0 开始）。
        text: 词的原始文本。
        start: 词在原文中的起始字符索引（含）。
        end: 词在原文中的结束字符索引（不含）。
        length: 词的字符长度。
    """

    index: int
    text: str
    start: int
    end: int
    length: int

    def to_dict(self) -> dict:
        """转换为字典格式，方便序列化。"""
        return {
            "index": self.index,
            "token": self.text,
            "start": self.start,
            "end": self.end,
            "length": self.length,
        }


# ============================================================
# 核心处理类
# ============================================================
class TextProcessor:
    """文本处理器，提供句子拆分和分词功能。

    Args:
        min_sentence_length: 句子最小长度，低于此值的片段会被丢弃。
            默认为 1。

    Example::

        >>> proc = TextProcessor(min_sentence_length=2)
        >>> proc.split_sentences("Hi. 这是测试。")
        ['这是测试。']
    """

    def __init__(self, min_sentence_length: int = _DEFAULT_MIN_SENTENCE_LENGTH) -> None:
        if not isinstance(min_sentence_length, int) or min_sentence_length < 1:
            raise ValueError(
                f"min_sentence_length 必须是正整数，收到: {min_sentence_length}"
            )
        self._min_sent_len = min_sentence_length

    # ----------------------------------------------------------
    # 句子拆分
    # ----------------------------------------------------------
    def split_sentences(self, text: str) -> List[str]:
        """将文本拆分为句子列表。

        拆分策略（按优先级）:
            1. 按中英文标点（``。！？.!?；;``）+ 后续空白拆分。
            2. 若策略 1 只产生 1 段，则按换行符拆分。
            3. 若以上均无法拆分，返回包含原文的单元素列表。

        Args:
            text: 待拆分的文本字符串。

        Returns:
            句子列表。空输入返回空列表。

        Raises:
            TypeError: 输入不是字符串时抛出。
        """
        if not isinstance(text, str):
            raise TypeError(f"期望 str 类型，收到 {type(text).__name__}")
        if not text.strip():
            logger.debug("split_sentences: 输入为空，返回 []")
            return []

        text = text.strip()

        # 策略 1: 按标点拆分
        raw_chunks = _SENT_SPLIT_RE.split(text)
        sentences = [
            chunk.strip()
            for chunk in raw_chunks
            if chunk.strip() and len(chunk.strip()) >= self._min_sent_len
        ]

        # 策略 2: 如果只拆出 1 段，尝试按换行拆分
        if len(sentences) <= 1:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if len(lines) > 1:
                logger.debug("回退到按换行拆分，得到 %d 个句子", len(lines))
                return lines

        # 策略 3: 兜底
        if sentences:
            logger.debug("按标点拆分得到 %d 个句子", len(sentences))
            return sentences

        return [text]

    # ----------------------------------------------------------
    # 分词
    # ----------------------------------------------------------
    def tokenize_with_spans(self, text: str) -> List[Token]:
        """按空白字符对文本进行分词，并记录每个词的字符偏移。

        Args:
            text: 待分词的文本字符串。

        Returns:
            ``Token`` 对象列表。空输入返回空列表。

        Raises:
            TypeError: 输入不是字符串时抛出。
        """
        if not isinstance(text, str):
            raise TypeError(f"期望 str 类型，收到 {type(text).__name__}")
        if not text:
            return []

        tokens: List[Token] = []
        for idx, match in enumerate(_WORD_RE.finditer(text)):
            word = match.group(0)
            tokens.append(
                Token(
                    index=idx,
                    text=word,
                    start=match.start(),
                    end=match.end(),
                    length=len(word),
                )
            )

        logger.debug("共切分出 %d 个 token", len(tokens))
        return tokens

    # ----------------------------------------------------------
    # 批量与统计接口
    # ----------------------------------------------------------
    def batch_split_sentences(self, texts: Sequence[str]) -> List[List[str]]:
        """批量对多段文本进行句子拆分。

        Args:
            texts: 文本列表。

        Returns:
            与输入等长的列表，每个元素为该文本的句子列表。
        """
        results: List[List[str]] = []
        for i, text in enumerate(texts):
            sentences = self.split_sentences(text)
            logger.debug("batch_split_sentences: 第 %d 段 -> %d 句", i, len(sentences))
            results.append(sentences)
        return results

    def get_sentence_count(self, text: str) -> int:
        """返回文本的句子数量。

        Args:
            text: 待统计的文本。

        Returns:
            句子数。
        """
        return len(self.split_sentences(text))


# ============================================================
# 模块级便捷函数（使用默认配置的快捷入口）
# ============================================================
_default_processor = TextProcessor()


def split_sentences(text: str) -> List[str]:
    """模块级快捷函数：拆分句子（使用默认配置）。

    等价于 ``TextProcessor().split_sentences(text)``。
    """
    return _default_processor.split_sentences(text)


def tokenize_with_spans(text: str) -> List[Token]:
    """模块级快捷函数：分词并返回位置信息（使用默认配置）。

    等价于 ``TextProcessor().tokenize_with_spans(text)``。
    """
    return _default_processor.tokenize_with_spans(text)


def get_sentence_count(text: str) -> int:
    """模块级快捷函数：统计句子数量（使用默认配置）。

    等价于 ``TextProcessor().get_sentence_count(text)``。
    """
    return _default_processor.get_sentence_count(text)