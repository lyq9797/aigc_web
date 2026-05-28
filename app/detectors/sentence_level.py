"""句子级别 AI 生成文本（AIGC）检测模块（核心检测功能其一）。

提供基于外部推理后端或词级别信号聚合的句子级检测能力。
优先调用外部独立脚本进行高精度推理；若不可用，则通过聚合词级别标签
推断句子属性；在无任何先验信号时，提供安全的默认回退策略。
"""

from __future__ import annotations

import json
import logging
import subprocess  # nosec B404 命令内部构造，无用户输入，安全可控
import sys
from dataclasses import dataclass
from typing import Any, TypedDict

from ..config import SENTENCE_BACKEND_SCRIPT
from .utils import split_sentences

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量定义
# ---------------------------------------------------------------------------

# 标签与模型标识
LABEL_AIGT: str = "AIGT"
LABEL_HWT: str = "HWT"
LABEL_ID_AIGT: int = 1

MODEL_EXTERNAL: str = "work1-test-single"
MODEL_AGGREGATED: str = "aggregated-word-signal"
MODEL_FALLBACK: str = "fallback-no-word-signal"

# 外部后端调用配置
EXTERNAL_BACKEND_TIMEOUT: int = 45  # 秒

# 置信度计算参数
DEFAULT_CONFIDENCE: float = 0.5
MAX_CONFIDENCE: float = 0.99
CONFIDENCE_OFFSET: float = 0.5


# ---------------------------------------------------------------------------
# 数据结构定义
# ---------------------------------------------------------------------------

class SentenceInfo(TypedDict, total=False):
    """句子级预测结果字典的类型定义。

    Attributes:
        index: 句子在原文中的顺序索引。
        text: 句子的原始文本内容。
        label: 预测标签（'AIGT' 或 'HWT'）。
        confidence: 预测置信度 (0.0 ~ 1.0)。
        ai_ratio: 句子内 AI 生成词元的比例 (0.0 ~ 1.0)。
    """

    index: int
    text: str
    label: str
    confidence: float
    ai_ratio: float


@dataclass
class SentencePredictResult:
    """句子级别预测结果封装。

    Attributes:
        sentences: 包含每个句子预测信息的列表。
        switch_sentence_index: 首个被判定为 AIGT 的句子索引（切换点）。
        model_used: 实际使用的检测策略/模型标识。
    """

    sentences: list[dict[str, Any]]
    switch_sentence_index: int
    model_used: str


# ---------------------------------------------------------------------------
# 核心检测器
# ---------------------------------------------------------------------------

class SentenceLevelDetector:
    """句子级别 AIGC 检测器。

    检测策略优先级：
    1. **外部后端推理**：调用配置的外部 Python 脚本（如 `test_single_text.py`）进行高精度检测。
    2. **词级信号聚合**：若外部后端不可用且提供了词级预测结果，则通过多数投票机制聚合出句子标签。
    3. **无信号回退**：若既无外部后端也无词级信号，则默认所有句子为人类撰写（HWT）。
    """

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def predict(
        self,
        text: str,
        words: list[dict[str, Any]] | None = None,
    ) -> SentencePredictResult:
        """对输入文本进行句子级别 AIGC 检测。

        Args:
            text: 待检测的完整文本。
            words: 可选的词级别预测结果列表。若提供，将在外部后端不可用时用于聚合。

        Returns:
            包含句子级预测结果的 `SentencePredictResult` 对象。
        """
        # 策略 1：尝试调用外部高精度后端
        external_result = self._call_external_backend(text)
        if external_result is not None:
            return external_result

        # 策略 2：基于词级信号聚合
        if words is not None:
            return self._aggregate_from_words(text, words)

        # 策略 3：无先验信号的安全回退
        return self._fallback_without_words(text)

    # ------------------------------------------------------------------
    # 外部后端调用
    # ------------------------------------------------------------------

    def _call_external_backend(self, text: str) -> SentencePredictResult | None:
        """调用外部独立脚本进行句子级推理。

        Args:
            text: 待检测文本。

        Returns:
            解析后的预测结果；若后端不可用或调用失败则返回 `None`。
        """
        script_path = str(SENTENCE_BACKEND_SCRIPT or "").strip()
        if not script_path:
            return None

        command = [
            sys.executable,
            script_path,
            "--single_text", text,
            "--output_json",
        ]

        try:
            completed = subprocess.run(  # nosec B603 命令内部构造，无用户输入，安全可控
                command,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=EXTERNAL_BACKEND_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            logger.warning("External sentence backend timed out.")
            return None
        except subprocess.CalledProcessError as exc:
            logger.warning(
                "External sentence backend failed (code=%d): %s",
                exc.returncode,
                exc.stderr[:200] if exc.stderr else "",
            )
            return None
        except Exception:
            logger.exception("Unexpected error calling external sentence backend.")
            return None

        return self._parse_external_output(completed.stdout)

    def _parse_external_output(self, stdout: str) -> SentencePredictResult | None:
        """解析外部后端的标准输出 JSON 数据。

        Args:
            stdout: 外部脚本的标准输出字符串。

        Returns:
            解析后的预测结果；若输出格式无效则返回 `None`。
        """
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        if not lines:
            logger.warning("External sentence backend returned empty output.")
            return None

        try:
            # 约定：有效的 JSON 载荷位于输出的最后一行
            payload = json.loads(lines[-1])
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse external backend JSON: %s", exc)
            return None

        rows_raw = payload.get("sentences", [])
        if not rows_raw:
            return None

        sentences: list[dict[str, Any]] = []
        for idx, item in enumerate(rows_raw):
            raw_label = str(item.get("label", LABEL_HWT)).upper()
            is_ai = raw_label == LABEL_AIGT

            sentences.append(
                {
                    "index": idx,
                    "text": str(item.get("text", "")),
                    "label": LABEL_AIGT if is_ai else LABEL_HWT,
                    "confidence": round(float(item.get("confidence", DEFAULT_CONFIDENCE)), 4),
                    "ai_ratio": round(
                        float(item.get("ai_ratio", 1.0 if is_ai else 0.0)), 4
                    ),
                }
            )

        switch_idx = int(
            payload.get("switch_sentence_index", self._find_first_aigt_index(sentences))
        )

        return SentencePredictResult(
            sentences=sentences,
            switch_sentence_index=switch_idx,
            model_used=MODEL_EXTERNAL,
        )

    # ------------------------------------------------------------------
    # 词级信号聚合与回退策略
    # ------------------------------------------------------------------

    def _aggregate_from_words(
        self,
        text: str,
        words: list[dict[str, Any]],
    ) -> SentencePredictResult:
        """基于词级别预测结果聚合生成句子级别结果。

        通过计算每个句子内 AI 词元的比例（多数投票）来决定句子标签。

        Args:
            text: 完整原文。
            words: 词级别预测结果列表（需包含 `start`, `end`, `label_id` 字段）。

        Returns:
            聚合后的句子级预测结果。
        """
        sentences_text = split_sentences(text)
        if not sentences_text:
            return SentencePredictResult(
                sentences=[], switch_sentence_index=0, model_used=MODEL_AGGREGATED
            )

        sentence_rows: list[dict[str, Any]] = []
        cursor = 0

        for idx, sent in enumerate(sentences_text):
            # 定位句子在原文中的确切跨度
            start = text.find(sent, cursor)
            if start < 0:
                start = cursor
            end = start + len(sent)
            cursor = end

            # 提取属于当前句子的词元
            within = [w for w in words if w["start"] >= start and w["end"] <= end]

            if not within:
                ai_ratio = 0.0
                confidence = DEFAULT_CONFIDENCE
            else:
                ai_count = sum(1 for w in within if w.get("label_id") == LABEL_ID_AIGT)
                ai_ratio = ai_count / len(within)
                # 置信度随 AI 比例偏离 0.5 的程度而增加
                confidence = MAX_CONFIDENCE if ai_ratio in (0.0, 1.0) else (
                    CONFIDENCE_OFFSET + abs(ai_ratio - CONFIDENCE_OFFSET)
                )
                confidence = min(MAX_CONFIDENCE, confidence)

            label = LABEL_AIGT if ai_ratio >= CONFIDENCE_OFFSET else LABEL_HWT
            sentence_rows.append(
                {
                    "index": idx,
                    "text": sent,
                    "label": label,
                    "confidence": round(float(confidence), 4),
                    "ai_ratio": round(float(ai_ratio), 4),
                }
            )

        return SentencePredictResult(
            sentences=sentence_rows,
            switch_sentence_index=self._find_first_aigt_index(sentence_rows),
            model_used=MODEL_AGGREGATED,
        )

    def _fallback_without_words(self, text: str) -> SentencePredictResult:
        """无词级信号时的安全回退策略。

        将所有句子默认标记为人类撰写（HWT），置信度设为 0.5。

        Args:
            text: 待检测文本。

        Returns:
            默认全为 HWT 的句子级预测结果。
        """
        sentences_text = split_sentences(text)
        rows = [
            {
                "index": idx,
                "text": sent,
                "label": LABEL_HWT,
                "confidence": DEFAULT_CONFIDENCE,
                "ai_ratio": 0.0,
            }
            for idx, sent in enumerate(sentences_text)
        ]

        return SentencePredictResult(
            sentences=rows,
            switch_sentence_index=0,
            model_used=MODEL_FALLBACK,
        )

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _find_first_aigt_index(sentence_rows: list[dict[str, Any]]) -> int:
        """查找句子列表中首个被标记为 AIGT 的句子索引。

        Args:
            sentence_rows: 句子预测结果列表。

        Returns:
            首个 AIGT 句子的 `index` 值；若不存在则返回 0。
        """
        for row in sentence_rows:
            if row.get("label") == LABEL_AIGT:
                return int(row.get("index", 0))
        return 0
# ============================================
# 补充说明：sentence_level.py 代码注释维护
# 提交日期标识：2026.3.15
# 脚本执行时间：2026-05-28 11:19:43
# ============================================

# ============================================
# 补充说明：sentence_level.py 代码注释维护
# 提交日期标识：2026.3.15
# 脚本执行时间：2026-05-28 11:24:06
# ============================================

# ============================================
# 补充说明：sentence_level.py 代码注释维护
# 提交日期标识：2026.3.16
# 脚本执行时间：2026-05-28 11:24:47
# ============================================

# ============================================
# 补充说明：sentence_level.py 代码注释维护
# 提交日期标识：2026.3.19
# 脚本执行时间：2026-05-28 11:25:26
# ============================================

# ============================================
# 补充说明：sentence_level.py 代码注释维护
# 提交日期标识：2026.3.22
# 脚本执行时间：2026-05-28 11:26:06
# ============================================

# ============================================
# 补充说明：sentence_level.py 代码注释维护
# 提交日期标识：2026.3.24
# 脚本执行时间：2026-05-28 11:26:48
# ============================================

# ============================================
# 补充说明：sentence_level.py 代码注释维护
# 提交日期标识：2026.3.27
# 脚本执行时间：2026-05-28 11:35:38
# ============================================

# ============================================
# 补充说明：sentence_level.py 代码注释维护
# 提交日期标识：2026.3.28
# 脚本执行时间：2026-05-28 11:36:26
# ============================================

# ============================================
# 补充说明：sentence_level.py 代码注释维护
# 提交日期标识：2026.3.31
# 脚本执行时间：2026-05-28 11:37:12
# ============================================

# ============================================
# 补充说明：sentence_level.py 代码注释维护
# 提交日期标识：2026.4.5
# 脚本执行时间：2026-05-28 12:03:25
# ============================================

# ============================================
# 补充说明：sentence_level.py 代码注释维护
# 提交日期标识：2026.4.6
# 脚本执行时间：2026-05-28 12:04:09
# ============================================

# ============================================
# 补充说明：sentence_level.py 代码注释维护
# 提交日期标识：2026.4.8
# 脚本执行时间：2026-05-28 12:06:06
# ============================================
