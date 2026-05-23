from __future__ import annotations

import json
import subprocess # nosec B404 命令内部构造，无用户输入，安全可控
import sys
from dataclasses import dataclass
from typing import Any

from ..config import SENTENCE_BACKEND_SCRIPT
from .utils import split_sentences


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
            return None

        # External script is expected to support a lightweight single-text mode.
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
            )# nosec B603 命令内部构造，无用户输入，安全可控
            lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
            if not lines:
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
                return None

            return SentencePredictResult(
                sentences=rows,
                switch_sentence_index=int(payload.get("switch_sentence_index", self._compute_switch_idx(rows))),
                model_used="work1-test-single",
            )
        except Exception:
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
        external = self._call_external_backend(text)
        if external is not None:
            return external

        if words is not None:
            return self._aggregate_from_words(text, words)

        return self._fallback_without_words(text)
