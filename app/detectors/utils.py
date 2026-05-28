"""文本预处理与分词工具模块。

提供基于正则表达式的轻量级句子分割（Sentence Splitting）和词元化（Tokenization）功能。
主要用于 AIGC 检测流水线中的文本预处理阶段，支持中英文混合标点及空白符分词。
"""

from __future__ import annotations

import re
from typing import TypedDict


# ---------------------------------------------------------------------------
# 正则表达式常量
# ---------------------------------------------------------------------------

# 句子分割正则：匹配中英文句末标点（。！？.!?）后紧跟的一个或多个空白字符。
# 【安全说明】该正则使用简单的字符集和固定 Lookbehind，无嵌套量词，免疫 ReDoS 攻击。
SENT_SPLIT_RE = re.compile(r"(?<=[。！？.!?])\s+")

# 词元（Token）匹配正则：匹配一个或多个连续的非空白字符。
# 【安全说明】该正则仅为简单的贪婪匹配，无回溯风险，免疫 ReDoS 攻击。
WORD_RE = re.compile(r"\S+")


# ---------------------------------------------------------------------------
# 数据结构定义
# ---------------------------------------------------------------------------

class TokenInfo(TypedDict):
    """词元（Token）信息字典的类型定义。

    Attributes:
        index: 词元在文本中的顺序索引（从 0 开始）。
        token: 词元的原始文本内容。
        start: 词元在原文本中的起始字符索引（包含）。
        end: 词元在原文本中的结束字符索引（不包含）。
    """

    index: int
    token: str
    start: int
    end: int


# ---------------------------------------------------------------------------
# 核心功能函数
# ---------------------------------------------------------------------------

def split_sentences(text: str) -> list[str]:
    """将输入文本分割为句子列表。

    分割策略（按优先级回退）：
    1. 主策略：根据中英文句末标点（。！？.!?）及其后的空白符进行分割。
    2. 回退策略 1：若主策略未能分割出有效句子，则按换行符（行）进行分割。
    3. 回退策略 2：若文本无换行符且无标点，则将整个非空文本作为单句返回。

    Args:
        text: 待分割的原始文本。

    Returns:
        包含分割后句子的列表。如果输入为空或纯空白字符，则返回空列表。
    """
    if not text or not text.strip():
        return []

    cleaned_text = text.strip()

    # 策略 1：基于标点符号分割
    chunks = SENT_SPLIT_RE.split(cleaned_text)
    sentences = [chunk.strip() for chunk in chunks if chunk.strip()]
    if sentences:
        return sentences

    # 策略 2：基于换行符分割（处理无标准标点但存在换行的文本）
    line_sentences = [line.strip() for line in cleaned_text.splitlines() if line.strip()]
    if line_sentences:
        return line_sentences

    # 策略 3：兜底返回（整段文本作为单句）
    return [cleaned_text]


def tokenize_with_spans(text: str) -> list[TokenInfo]:
    """将文本词元化（Tokenize）并保留每个词元在原文中的位置跨度。

    以空白字符为分隔符，提取所有非空白字符序列作为词元（Token），
    并记录其索引、文本内容及在原文本中的起止位置。

    Args:
        text: 待词元化的原始文本。

    Returns:
        `TokenInfo` 字典列表，按词元在文本中出现的顺序排列。
        若文本为空或纯空白，则返回空列表。
    """
    return [
        TokenInfo(
            index=idx,
            token=match.group(0),
            start=match.start(),
            end=match.end(),
        )
        for idx, match in enumerate(WORD_RE.finditer(text))
    ]
