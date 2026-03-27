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

    # 外部后端重试配置
    MAX_RETRIES = 2
    RETRY_DELAY = 2.0  # 秒

    def _compute_switch_idx(self, sentence_rows: list[dict[str, Any]]) -> int:
        for row in sentence_rows:
            if row.get("label") == "AIGT":
                return int(row.get("index", 0))
        return 0

    def _run_external_once(self, cmd: list[str]) -> SentencePredictResult | None:
        """执行一次外部后端调用，成功返回结果，失败返回 None。"""
        completed = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=45,
        )
        lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        if not lines:
            logger.warning("外部后端未返回有效输出")
            return None

        payload = json.loads(lines[-1])
        rows_raw = payload.get("sentences", [])
        rows: list[dict[str, Any]] = []
        for idx, item in enumerate(rows_raw):
            label = str(item.get("label", "HWT")).upper()
            rows.append(
                {
                    "index": idx,
                    "text": str(item.get("text", "")),
                    "label": "AIGT" if label == "AIGT" else "HWT",
                    "confidence": round(float(item.get("confidence", 0.5)), 4),
                    "ai_ratio": round(float(item.get("ai_ratio", 1.0 if label == "AIGT" else 0.0)), 4),
                }
            )

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

        for attempt in range(1 + self.MAX_RETRIES):
            try:
                result = self._run_external_once(cmd)
                if result is not None:
                    return result
            except subprocess.TimeoutExpired:
                logger.error("外部后端调用超时（45秒），第 %d/%d 次尝试", attempt + 1, 1 + self.MAX_RETRIES)
            except subprocess.CalledProcessError as e:
                logger.error(
                    "外部后端执行失败，返回码: %d, stderr: %s，第 %d/%d 次尝试",
                    e.returncode, e.stderr, attempt + 1, 1 + self.MAX_RETRIES,
                )
            except json.JSONDecodeError:
                logger.error("外部后端返回的JSON解析失败，第 %d/%d 次尝试", attempt + 1, 1 + self.MAX_RETRIES)
            except Exception as e:
                logger.error("外部后端调用发生未知异常: %s，第 %d/%d 次尝试", e, attempt + 1, 1 + self.MAX_RETRIES)

            if attempt < self.MAX_RETRIES:
                logger.info("等待 %.1f 秒后重试...", self.RETRY_DELAY)
                time.sleep(self.RETRY_DELAY)

        logger.error("外部后端调用在 %d 次尝试后仍然失败", 1 + self.MAX_RETRIES)
        return None

    def _build_sentence_offsets(self, text: str, sents: list[str]) -> list[tuple[int, int]]:
        """
        根据分句结果计算每个句子在原文中的 (start, end) 偏移量。
        通过逐个字符累计偏移，避免 text.find 在重复子串时定位不准。
        """
        offsets: list[tuple[int, int]] = []
        cursor = 0
        for sent in sents:
            # 从当前光标位置开始查找，确保不会匹配到前面的重复子串
            pos = text.find(sent, cursor)
            if pos < 0:
                # 如果找不到，就用当前光标位置作为近似
                pos = cursor
            offsets.append((pos, pos + len(sent)))
            cursor = pos + len(sent)
        return offsets

    def _aggregate_from_words(self, text: str, words: list[dict[str, Any]]) -> SentencePredictResult:
        # 处理空文本
        if not text or not text.strip():
            logger.info("输入文本为空，返回空结果")
            return SentencePredictResult(sentences=[], switch_sentence_index=0, model_used="aggregated-word-signal")

        sents = split_sentences(text)
        if not sents:
            return SentencePredictResult(sentences=[], switch_sentence_index=0, model_used="aggregated-word-signal")

        # 预先计算所有句子的偏移量
        offsets = self._build_sentence_offsets(text, sents)

        sentence_rows: list[dict[str, Any]] = []
        for idx, sent in enumerate(sents):
            start, end = offsets[idx]

            # 找出落在当前句子范围内的词
            within = [w for w in words if w["start"] >= start and w["end"] <= end]
            if not within:
                ai_ratio = 0.0
                confidence = 0.5
            else:
                ai_count = sum(1 for w in within if w["label_id"] == 1)
                ai_ratio = ai_count / len(within)
                confidence = max(0.5, min(0.99, 0.5 + abs(ai_ratio - 0.5)))

            label = "AIGT" if ai_ratio >= 0.5 else "HWT"
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
                "confidence": 0.5,
                "ai_ratio": 0.0,
            }
            for idx, sent in enumerate(sents)
        ]
        return SentencePredictResult(
            sentences=rows,
            switch_sentence_index=0,
            model_used="fallback-no-word-signal",
        )

    def predict(self, text: str, words: list[dict[str, Any]] | None = None) -> SentencePredictResult:
        logger.info("开始句子级别检测，文本长度: %d", len(text))

        external = self._call_external_backend(text)
        if external is not None:
            logger.info("使用外部后端结果，模型: %s", external.model_used)
            return external

        if words is not None:
            logger.info("使用词级信号聚合策略，词数: %d", len(words))
            return self._aggregate_from_words(text, words)

        return self._fallback_without_words(text)