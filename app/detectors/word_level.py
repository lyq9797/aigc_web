from __future__ import annotations

import json
import logging
import subprocess # nosec B404 命令内部构造，无用户输入，安全可控
import sys
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..config import WORD_BOUNDARY_BACKEND_SCRIPT, WORD_MODEL_NAME, WORD_MODEL_PATH
from .utils import split_sentences, tokenize_with_spans

logger = logging.getLogger(__name__)


@dataclass
class WordPredictResult:
    words: list[dict[str, Any]]
    switch_word_index: int
    model_used: str


class WordLevelDetector:
    def __init__(self) -> None:
        self.model = None
        self.tokenizer = None
        self.device = None
        self.ready = False
        self.max_len = 512

        try:
            import torch
            from transformers import AutoTokenizer

            from .word_model_runtime import DeBERTaCRFTagger, infer_document_with_sliding_windows

            self._torch = torch
            self._infer_fn = infer_document_with_sliding_windows
            self.tokenizer = AutoTokenizer.from_pretrained(WORD_MODEL_NAME, revision="8ccc9b6f36199bec6961081d44eb72fb3f7353f3")
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.model = DeBERTaCRFTagger(WORD_MODEL_NAME, 2).to(self.device)
            ckpt = torch.load(WORD_MODEL_PATH, map_location=self.device, weights_only=True)
            state = ckpt.get("model_state_dict", ckpt)
            self.model.load_state_dict(state)
            self.model.eval()
            self.ready = True
            logger.info("Word model loaded from %s", WORD_MODEL_PATH)
        except Exception as exc:
            logger.warning("Word-level model not loaded, fallback mode enabled: %s", exc)

    def _fallback_predict(self, text: str) -> WordPredictResult:
        tokens = tokenize_with_spans(text)
        if not tokens:
            return WordPredictResult(words=[], switch_word_index=0, model_used="fallback-heuristic")

        lengths = np.array([len(t["token"]) for t in tokens], dtype=np.float32)
        if len(lengths) > 1:
            smooth = np.convolve(lengths, np.ones(3) / 3.0, mode="same")
            grad = np.abs(np.diff(smooth, prepend=smooth[0]))
            split_idx = int(np.argmax(grad))
        else:
            split_idx = 0

        words = []
        for i, item in enumerate(tokens):
            is_ai = i > split_idx
            confidence = 0.55 + min(0.4, abs(i - split_idx) * 0.03)
            words.append(
                {
                    **item,
                    "label": "AIGT" if is_ai else "HWT",
                    "label_id": 1 if is_ai else 0,
                    "confidence": round(float(confidence), 4),
                }
            )

        return WordPredictResult(words=words, switch_word_index=split_idx, model_used="fallback-heuristic")

    def predict(self, text: str) -> WordPredictResult:
        if not self.ready:
            return self._fallback_predict(text)

        tokens = tokenize_with_spans(text)
        words = [t["token"] for t in tokens]
        if not words:
            return WordPredictResult(words=[], switch_word_index=0, model_used="deberta-crf")

        pred_labels, boundary, vote_counts = self._infer_fn(
            self.model,
            words,
            self.tokenizer,
            self.max_len,
            self.device,
            base_window=512,
            base_stride=384,
            short_window_cap=256,
        )

        rows = []
        for i, token_item in enumerate(tokens):
            vote0 = int(vote_counts[i, 0]) if i < vote_counts.shape[0] else 0
            vote1 = int(vote_counts[i, 1]) if i < vote_counts.shape[0] else 0
            total = max(1, vote0 + vote1)
            conf = max(vote0, vote1) / total
            label_id = int(pred_labels[i]) if i < len(pred_labels) else 0
            rows.append(
                {
                    **token_item,
                    "label": "AIGT" if label_id == 1 else "HWT",
                    "label_id": label_id,
                    "confidence": round(float(conf), 4),
                }
            )

        return WordPredictResult(words=rows, switch_word_index=int(boundary), model_used="deberta-crf")

    def _sentence_spans(self, text: str, sentence_rows: list[dict[str, Any]]) -> list[tuple[int, int, str]]:
        spans: list[tuple[int, int, str]] = []
        cursor = 0
        for row in sentence_rows:
            sent = str(row.get("text", "")).strip()
            if not sent:
                continue
            start = text.find(sent, cursor)
            if start < 0:
                start = cursor
            end = start + len(sent)
            cursor = end
            label = "AIGT" if str(row.get("label", "")).upper() == "AIGT" else "HWT"
            spans.append((start, end, label))
        return spans

    def _compute_first_switch_word_index(self, labels: list[int]) -> int:
        if not labels:
            return 0
        for idx in range(1, len(labels)):
            if labels[idx] != labels[idx - 1]:
                return idx - 1
        return 0

    def _call_external_boundary_backend(self, text: str) -> int | None:
        script_path = str(WORD_BOUNDARY_BACKEND_SCRIPT or "").strip()
        if not script_path:
            return None

        cmd = [
            sys.executable,
            script_path,
            "--single_text",
            text,
            "--output_json",
            "--model_name",
            WORD_MODEL_NAME,
            "--best_model_path",
            WORD_MODEL_PATH,
            "--max_len",
            str(self.max_len),
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
            )# nosec B603 命令内部构造，无用户输入，shell=False，安全可控
            payload = json.loads(completed.stdout.strip())
            boundary_idx = int(payload.get("boundary_idx", 0))
            return boundary_idx
        except Exception:
            return None

    def predict_with_sentence_switches(self, text: str, sentence_rows: list[dict[str, Any]]) -> WordPredictResult:
        tokens = tokenize_with_spans(text)
        if not tokens:
            return WordPredictResult(words=[], switch_word_index=0, model_used="switch-aware-empty")

        if not sentence_rows:
            return self.predict(text)

        spans = self._sentence_spans(text, sentence_rows)
        if not spans:
            return self.predict(text)

        token_labels = [0 for _ in tokens]
        token_conf = [0.65 for _ in tokens]

        # Step 1: initialize token labels by sentence labels.
        sentence_token_indices: list[list[int]] = []
        for start, end, sent_label in spans:
            idxs = [
                i
                for i, tok in enumerate(tokens)
                if tok["start"] >= start and tok["end"] <= end
            ]
            sentence_token_indices.append(idxs)
            label_id = 1 if sent_label == "AIGT" else 0
            for i in idxs:
                token_labels[i] = label_id
                token_conf[i] = 0.7

        # Step 2~4: iterate over all sentence switch points and refine with local word boundary detector.
        for i in range(len(spans) - 1):
            left_label = spans[i][2]
            right_label = spans[i + 1][2]
            if left_label == right_label:
                continue

            left_idxs = sentence_token_indices[i]
            right_idxs = sentence_token_indices[i + 1]
            combined_idxs = left_idxs + right_idxs
            if not combined_idxs:
                continue

            left_text = text[spans[i][0] : spans[i][1]].strip()
            right_text = text[spans[i + 1][0] : spans[i + 1][1]].strip()
            local_text = f"{left_text} {right_text}".strip()
            if not local_text:
                continue

            local_boundary = self._call_external_boundary_backend(local_text)
            if local_boundary is None:
                local_res = self.predict(local_text)
                local_boundary = int(local_res.switch_word_index)
            local_boundary = max(0, min(local_boundary, len(combined_idxs) - 1))
            boundary_global = combined_idxs[local_boundary]

            left_id = 1 if left_label == "AIGT" else 0
            right_id = 1 if right_label == "AIGT" else 0
            for gi in combined_idxs:
                if gi <= boundary_global:
                    token_labels[gi] = left_id
                else:
                    token_labels[gi] = right_id
                token_conf[gi] = 0.88

        rows: list[dict[str, Any]] = []
        for i, tok in enumerate(tokens):
            lid = int(token_labels[i])
            rows.append(
                {
                    **tok,
                    "label": "AIGT" if lid == 1 else "HWT",
                    "label_id": lid,
                    "confidence": round(float(token_conf[i]), 4),
                }
            )

        switch_idx = self._compute_first_switch_word_index(token_labels)
        return WordPredictResult(
            words=rows,
            switch_word_index=switch_idx,
            model_used="switch-aware-deberta-crf",
        )
