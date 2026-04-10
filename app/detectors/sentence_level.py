# app/detector/sentence_level.py
from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any

from ..config import SENTENCE_BACKEND_SCRIPT
from .utils import split_sentences

logger = logging.getLogger(__name__)


@dataclass
class SentencePredictResult:
    sentences: list[dict[str, Any]]
    switch_sentence_index: int
    model_used: str


class SentenceLevelDetector:
    """
    Sentence-level detector.

    Notes:
        - Primary external backend is F:\\wy\\work1_single\\test_single_text.py.
        - If external backend is unavailable, fallback uses sentence-wise aggregation
            from word-level signals.
        - External backend calls include automatic retry (up to 2 retries).
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

    def _compute_switch_idx(self, sentence_rows: list[dict[str, Any]]) -> int:
        """找到第一个被标记为 AIGT 的句子的索引，没有则返回 0。"""
        for row in sentence_rows:
            if row.get("label") == "AIGT":
                return int(row.get("index", 0))
        return 0

    def _parse_external_rows(self, rows_raw: list[dict]) -> list[dict[str, Any]]:
        """解析外部后端返回的原始句子数据为标准格式。"""
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
        """执行一次外部后端调用，成功返回结果，失败返回 None。"""
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
                logger.error("外部后端调用超时（%d秒），第 %d/%d 次尝试", self.BACKEND_TIMEOUT, attempt + 1, total_attempts)
            except subprocess.CalledProcessError as e:
                logger.error(
                    "外部后端执行失败，返回码: %d, stderr: %s，第 %d/%d 次尝试",
                    e.returncode, e.stderr, attempt + 1, total_attempts,
                )
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
        """
        根据分句结果计算每个句子在原文中的 (start, end) 偏移量。
        通过逐个字符累计偏移，避免 text.find 在重复子串时定位不准。
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

    def _compute_sentence_ai_score(self, within_words: list[dict[str, Any]]) -> tuple[float, float, str]:
        """
        根据句子内的词级预测结果，计算 AI 占比、置信度和标签。
        返回 (ai_ratio, confidence, label)。
        """
        if not within_words:
            return 0.0, self.DEFAULT_CONFIDENCE, "HWT"

        # 过滤掉缺少必要字段的异常词数据
        valid_words = [w for w in within_words if "label_id" in w]
        if not valid_words:
            return 0.0, self.DEFAULT_CONFIDENCE, "HWT"

        ai_count = sum(1 for w in valid_words if w["label_id"] == 1)
        ai_ratio = ai_count / len(valid_words)
        confidence = max(self.CONFIDENCE_FLOOR, min(self.CONFIDENCE_CEIL, self.CONFIDENCE_FLOOR + abs(ai_ratio - self.AI_RATIO_THRESHOLD)))
        label = "AIGT" if ai_ratio >= self.AI_RATIO_THRESHOLD else "HWT"

        return ai_ratio, confidence, label

    def _aggregate_from_words(self, text: str, words: list[dict[str, Any]]) -> SentencePredictResult:
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

            within = [w for w in words if w.get("start") is not None and w.get("end") is not None
                      and w["start"] >= start and w["end"] <= end]

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
        logger.info("使用无词信号的兜底策略")
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
        # ---- 输入校验 ----
        if not isinstance(text, str):
            logger.warning("predict 收到非字符串类型输入: %s，转为空字符串处理", type(text))
            text = ""

        if not text.strip():
            logger.info("输入文本为空，直接返回空结果")
            return SentencePredictResult(sentences=[], switch_sentence_index=0, model_used="empty-input")

        logger.info("开始句子级别检测，文本长度: %d", len(text))

        external = self._call_external_backend(text)
        if external is not None:
            logger.info("使用外部后端结果，模型: %s", external.model_used)
            return external

        if words is not None:
            logger.info("使用词级信号聚合策略，词数: %d", len(words))
            return self._aggregate_from_words(text, words)

        return self._fallback_without_words(text)