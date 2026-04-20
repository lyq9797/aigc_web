# app/detector/sentence_level.py
from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from typing import Any

from ..config import SENTENCE_BACKEND_SCRIPT
from .utils import split_sentences

logger = logging.getLogger(__name__)


@dataclass
class SentencePredictResult:
    """句子级别检测的结果。

    Attributes:
        sentences: 每个句子的检测结果列表，每项包含 index, text, label, confidence, ai_ratio。
        switch_sentence_index: 第一个被判定为 AIGT 的句子索引，用于标记"切换点"。
        model_used: 本次检测所使用的模型/策略名称。
    """
    sentences: list[dict[str, Any]]
    switch_sentence_index: int
    model_used: str

    def to_dict(self) -> dict[str, Any]:
        """将结果转换为字典，便于 JSON 序列化。

        Returns:
            包含所有字段的字典。
        """
        return asdict(self)

    def __repr__(self) -> str:
        return (
            f"SentencePredictResult("
            f"num_sentences={len(self.sentences)}, "
            f"switch_idx={self.switch_sentence_index}, "
            f"model='{self.model_used}')"
        )


class SentenceLevelDetector:
    """
    句子级别的 AIGT（AI-Generated Text）检测器。

    检测策略优先级：
        1. 调用外部后端脚本（work1_single/test_single_text.py）获取结果。
        2. 如果外部后端不可用，基于词级信号按句子聚合判定。
        3. 如果词级信号也没有，使用兜底策略（全部标为 HWT）。

    Notes:
        - 外部后端调用支持自动重试（最多 2 次）。
        - 所有置信度和 AI 占比均保留 4 位小数。
    """

    # ---- 外部后端配置 ----
    MAX_RETRIES = 2
    RETRY_DELAY = 2.0          # 重试间隔（秒）
    BACKEND_TIMEOUT = 45       # 外部脚本超时（秒）

    # ---- 置信度计算相关阈值 ----
    CONFIDENCE_FLOOR = 0.5     # 最低置信度
    CONFIDENCE_CEIL = 0.99     # 最高置信度
    DEFAULT_CONFIDENCE = 0.5   # 无词匹配时的默认置信度

    # ---- 标签判定阈值 ----
    AI_RATIO_THRESHOLD = 0.5   # AI词占比 >= 该值则判定为 AIGT

    # ---- 默认 AI ratio ----
    DEFAULT_AI_RATIO_HWT = 0.0
    DEFAULT_AI_RATIO_AIGT = 1.0

    def __repr__(self) -> str:
        return (
            f"SentenceLevelDetector("
            f"max_retries={self.MAX_RETRIES}, "
            f"timeout={self.BACKEND_TIMEOUT}s)"
        )

    def _compute_switch_idx(self, sentence_rows: list[dict[str, Any]]) -> int:
        """找到第一个被标记为 AIGT 的句子的索引。

        Args:
            sentence_rows: 句子检测结果列表。

        Returns:
            第一个 AIGT 句子的索引；如果没有 AIGT 句子，返回 0。
        """
        for row in sentence_rows:
            if row.get("label") == "AIGT":
                return int(row.get("index", 0))
        return 0

    def _parse_external_rows(self, rows_raw: list[dict]) -> list[dict[str, Any]]:
        """解析外部后端返回的原始句子数据为标准格式。

        Args:
            rows_raw: 外部后端 JSON 中的 sentences 列表。

        Returns:
            标准化后的句子结果列表。
        """
        rows: list[dict[str, Any]] = []
        for idx, item in enumerate(rows_raw):
            label = str(item.get("label", "HWT")).upper()
            is_ai = (label == "AIGT")
            default_ai_ratio = self.DEFAULT_AI_RATIO_AIGT if is_ai else self.DEFAULT_AI_RATIO_HWT
            rows.append(
                {
                    "index": idx,
                    "text": str(item.get("text", "")),
                    "label": "AIGT" if is_ai else "HWT",
                    "confidence": round(float(item.get("confidence", self.DEFAULT_CONFIDENCE)), 4),
                    "ai_ratio": round(float(item.get("ai_ratio", default_ai_ratio)), 4),
                }
            )
        return rows

    def _run_external_once(self, cmd: list[str]) -> SentencePredictResult | None:
        """执行一次外部后端调用。

        Args:
            cmd: 要执行的命令行参数列表。

        Returns:
            成功时返回 SentencePredictResult，失败时返回 None。
        """
        completed = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=self.BACKEND_TIMEOUT,
        )
        lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        if not lines:
            logger.warning("外部后端未返回有效输出")
            return None

        payload = json.loads(lines[-1])
        rows_raw = payload.get("sentences", [])
        rows = self._parse_external_rows(rows_raw)

        if not rows:
            logger.warning("外部后端返回的句子列表为空")
            return None

        logger.info("外部后端成功返回 %d 个句子结果", len(rows))
        return SentencePredictResult(
            sentences=rows,
            switch_sentence_index=int(payload.get("switch_sentence_index", self._compute_switch_idx(rows))),
            model_used="work1-test-single",
        )

    def _call_external_backend(self, text: str) -> SentencePredictResult | None:
        """调用外部后端脚本进行句子检测（带重试）。

        Args:
            text: 待检测的文本。

        Returns:
            成功时返回 SentencePredictResult，所有重试均失败时返回 None。
        """
        script_path = str(SENTENCE_BACKEND_SCRIPT or "").strip()
        if not script_path:
            logger.info("外部后端脚本路径未配置，跳过外部调用")
            return None

        logger.info("正在调用外部后端脚本: %s", script_path)

        cmd = [
            sys.executable,
            script_path,
            "--single_text",
            text,
            "--output_json",
        ]

        total_attempts = 1 + self.MAX_RETRIES
        for attempt in range(total_attempts):
            try:
                result = self._run_external_once(cmd)
                if result is not None:
                    return result
            except subprocess.TimeoutExpired:
                logger.error("外部后端调用超时（%d秒），第 %d/%d 次尝试",
                             self.BACKEND_TIMEOUT, attempt + 1, total_attempts)
            except subprocess.CalledProcessError as e:
                logger.error("外部后端执行失败，返回码: %d, stderr: %s，第 %d/%d 次尝试",
                             e.returncode, e.stderr, attempt + 1, total_attempts)
            except json.JSONDecodeError:
                logger.error("外部后端返回的JSON解析失败，第 %d/%d 次尝试", attempt + 1, total_attempts)
            except Exception as e:
                logger.error("外部后端调用发生未知异常: %s，第 %d/%d 次尝试", e, attempt + 1, total_attempts)

            if attempt < self.MAX_RETRIES:
                logger.info("等待 %.1f 秒后重试...", self.RETRY_DELAY)
                time.sleep(self.RETRY_DELAY)

        logger.error("外部后端调用在 %d 次尝试后仍然失败", total_attempts)
        return None

    def _build_sentence_offsets(self, text: str, sents: list[str]) -> list[tuple[int, int]]:
        """计算每个句子在原文中的 (start, end) 字符偏移量。

        Args:
            text: 原始文本。
            sents: 分句后的句子列表。

        Returns:
            与 sents 等长的 (start, end) 偏移量列表。
        """
        offsets: list[tuple[int, int]] = []
        cursor = 0
        for sent in sents:
            pos = text.find(sent, cursor)
            if pos < 0:
                pos = cursor
            offsets.append((pos, pos + len(sent)))
            cursor = pos + len(sent)
        return offsets

    def _compute_sentence_ai_score(
        self, within_words: list[dict[str, Any]]
    ) -> tuple[float, float, str]:
        """根据句子内的词级预测结果，计算 AI 占比、置信度和标签。

        Args:
            within_words: 落在当前句子范围内的词级检测结果。

        Returns:
            (ai_ratio, confidence, label) 三元组。
        """
        if not within_words:
            return 0.0, self.DEFAULT_CONFIDENCE, "HWT"

        # 过滤掉缺少必要字段的异常词数据
        valid_words = [w for w in within_words if "label_id" in w]
        if not valid_words:
            return 0.0, self.DEFAULT_CONFIDENCE, "HWT"

        ai_count = sum(1 for w in valid_words if w["label_id"] == 1)
        ai_ratio = ai_count / len(valid_words)
        confidence = max(
            self.CONFIDENCE_FLOOR,
            min(self.CONFIDENCE_CEIL, self.CONFIDENCE_FLOOR + abs(ai_ratio - self.AI_RATIO_THRESHOLD)),
        )
        label = "AIGT" if ai_ratio >= self.AI_RATIO_THRESHOLD else "HWT"

        return ai_ratio, confidence, label

    def _aggregate_from_words(self, text: str, words: list[dict[str, Any]]) -> SentencePredictResult:
        """基于词级信号聚合生成句子级别检测结果。

        Args:
            text: 待检测的原始文本。
            words: 词级检测结果列表，每项需包含 start, end, label_id 字段。

        Returns:
            句子级别的检测结果。
        """
        if not text or not text.strip():
            logger.info("输入文本为空，返回空结果")
            return SentencePredictResult(sentences=[], switch_sentence_index=0, model_used="aggregated-word-signal")

        sents = split_sentences(text)
        if not sents:
            return SentencePredictResult(sentences=[], switch_sentence_index=0, model_used="aggregated-word-signal")

        offsets = self._build_sentence_offsets(text, sents)

        sentence_rows: list[dict[str, Any]] = []
        for idx, sent in enumerate(sents):
            start, end = offsets[idx]

            within = [
                w for w in words
                if w.get("start") is not None
                and w.get("end") is not None
                and w["start"] >= start
                and w["end"] <= end
            ]

            ai_ratio, confidence, label = self._compute_sentence_ai_score(within)

            sentence_rows.append(
                {
                    "index": idx,
                    "text": sent,
                    "label": label,
                    "confidence": round(float(confidence), 4),
                    "ai_ratio": round(float(ai_ratio), 4),
                }
            )

        switch_idx = self._compute_switch_idx(sentence_rows)

        return SentencePredictResult(
            sentences=sentence_rows,
            switch_sentence_index=switch_idx,
            model_used="aggregated-word-signal",
        )

    def _fallback_without_words(self, text: str) -> SentencePredictResult:
        """兜底策略：无词级信号时，将所有句子标记为 HWT。

        Args:
            text: 待检测的原始文本。

        Returns:
            所有句子均标记为 HWT 的结果。
        """
        logger.info("使用无词信号的兜底策略")

        if not text or not text.strip():
            return SentencePredictResult(sentences=[], switch_sentence_index=0, model_used="fallback-no-word-signal")

        sents = split_sentences(text)
        rows = [
            {
                "index": idx,
                "text": sent,
                "label": "HWT",
                "confidence": self.DEFAULT_CONFIDENCE,
                "ai_ratio": self.DEFAULT_AI_RATIO_HWT,
            }
            for idx, sent in enumerate(sents)
        ]
        return SentencePredictResult(
            sentences=rows,
            switch_sentence_index=0,
            model_used="fallback-no-word-signal",
        )

    def predict(self, text: str, words: list[dict[str, Any]] | None = None) -> SentencePredictResult:
        """执行句子级别的 AIGT 检测。

        按优先级依次尝试：外部后端 → 词级聚合 → 兜底策略。

        Args:
            text: 待检测的文本字符串。
            words: 可选的词级检测结果列表。如果提供，当外部后端不可用时
                   将基于词级信号进行句子聚合。

        Returns:
            SentencePredictResult 对象，包含每个句子的检测结果和切换点索引。
        """
        # ---- 输入校验 ----
        if not isinstance(text, str):
            logger.warning("predict 收到非字符串类型输入: %s，转为空字符串处理", type(text))
            text = ""

        if not text.strip():
            logger.info("输入文本为空，直接返回空结果")
            return SentencePredictResult(sentences=[], switch_sentence_index=0, model_used="empty-input")

        logger.info("开始句子级别检测，文本长度: %d", len(text))

        # 策略1：尝试外部后端
        external = self._call_external_backend(text)
        if external is not None:
            logger.info("使用外部后端结果，模型: %s", external.model_used)
            return external

        # 策略2：基于词级信号聚合
        if words is not None:
            logger.info("使用词级信号聚合策略，词数: %d", len(words))
            return self._aggregate_from_words(text, words)

        # 策略3：兜底
        return self._fallback_without_words(text)