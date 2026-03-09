# app/detector/sentence_level.py
from __future__ import annotations

import json
import logging
import subprocess
import sys
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
    """

    def _compute_switch_idx(self, sentence_rows: list[dict[str, Any]]) -> int:
        for row in sentence_rows:
            if row.get("label") == "AIGT":
                return int(row.get("index", 0))
        return 0

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

        try:
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
        except subprocess.TimeoutExpired:
            logger.error("外部后端调用超时（45秒）")
            return None
        except subprocess.CalledProcessError as e:
            logger.error("外部后端执行失败，返回码: %d, stderr: %s", e.returncode, e.stderr)
            return None
        except json.JSONDecodeError:
            logger.error("外部后端返回的JSON解析失败")
            return None
        except Exception as e:
            logger.error("外部后端调用发生未知异常: %s", e)
            return None

    def _aggregate_from_words(self, text: str, words: list[dict[str, Any]]) -> SentencePredictResult:
        sents = split_sentences(text)
        if not sents:
            return SentencePredictResult(sentences=[], switch_sentence_index=0, model_used="aggregated-word-signal")

        cursor = 0
        sentence_rows: list[dict[str, Any]] = []
        for idx, sent in enumerate(sents):
            start = text.find(sent, cursor)
            if start < 0:
                start = cursor
            end = start + len(sent)
            cursor = end

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