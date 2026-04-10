from __future__ import annotations

import json
import logging
import subprocess
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
    BASE_WINDOW: int = 512
    BASE_STRIDE: int = 384
    SHORT_WINDOW_CAP: int = 256
    NUM_LABELS: int = 2

    FALLBACK_BASE_CONFIDENCE: float = 0.55
    FALLBACK_MAX_CONFIDENCE_BOOST: float = 0.4
    FALLBACK_CONFIDENCE_STEP: float = 0.03
    DEFAULT_TOKEN_CONFIDENCE: float = 0.65
    SENTENCE_TOKEN_CONFIDENCE: float = 0.7
    SWITCH_REFINED_CONFIDENCE: float = 0.88

    BACKEND_TIMEOUT_SECONDS: int = 45
    HEURISTIC_MIN_TOKENS_FOR_CONV: int = 4

    def __init__(self) -> None:
        self.model = None
        self.tokenizer = None
        self.device = None
        self.ready = False
        self.max_len = self.BASE_WINDOW

        try:
            import torch
            from transformers import AutoTokenizer

            from .word_model_runtime import DeBERTaCRFTagger, infer_document_with_sliding_windows

            self._torch = torch
            self._infer_fn = infer_document_with_sliding_windows
            self.tokenizer = AutoTokenizer.from_pretrained(WORD_MODEL_NAME)
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.model = DeBERTaCRFTagger(WORD_MODEL_NAME, self.NUM_LABELS).to(self.device)
            ckpt = torch.load(WORD_MODEL_PATH, map_location=self.device, weights_only=False)
            state = ckpt.get("model_state_dict", ckpt)
            self.model.load_state_dict(state)
            self.model.eval()
            self.ready = True
            logger.info("Word model loaded successfully from %s on %s", WORD_MODEL_PATH, self.device)
        except FileNotFoundError:
            logger.warning("Model file not found: %s. Fallback mode enabled.", WORD_MODEL_PATH)
        except ImportError as exc:
            logger.warning("Required dependency missing: %s. Fallback mode enabled.", exc)
        except Exception as exc:
            logger.warning("Word-level model not loaded, fallback mode enabled: %s", exc, exc_info=True)

    # ---- 辅助方法 ----

    def _heuristic_split_index(self, tokens: list[dict[str, Any]]) -> int:
        """基于词长梯度计算启发式切换点。"""
        n = len(tokens)
        if n <= 1:
            return 0
        if n < self.HEURISTIC_MIN_TOKENS_FOR_CONV:
            return n // 2

        lengths = np.array([len(t["token"]) for t in tokens], dtype=np.float32)
        smooth = np.convolve(lengths, np.ones(3) / 3.0, mode="same")
        grad = np.abs(np.diff(smooth, prepend=smooth[0]))
        return int(np.argmax(grad))

    def _build_word_row(
        self, token_item: dict[str, Any], label_id: int, confidence: float
    ) -> dict[str, Any]:
        """统一构造单条 word 结果字典。"""
        return {
            **token_item,
            "label": "AIGT" if label_id == 1 else "HWT",
            "label_id": label_id,
            "confidence": round(float(confidence), 4),
        }

    def _compute_fallback_confidence(self, token_index: int, split_index: int) -> float:
        """计算 fallback 模式下某个 token 的置信度。"""
        return self.FALLBACK_BASE_CONFIDENCE + min(
            self.FALLBACK_MAX_CONFIDENCE_BOOST,
            abs(token_index - split_index) * self.FALLBACK_CONFIDENCE_STEP,
        )

    @staticmethod
    def _label_to_id(label: str) -> int:
        """V4: 将标签字符串映射为整数 ID。"""
        return 1 if label.upper() == "AIGT" else 0

    # ---- 核心推理 ----

    def _fallback_predict(self, text: str) -> WordPredictResult:
        if not isinstance(text, str):
            raise TypeError(f"Expected str, got {type(text).__name__}")
        text = text.strip()

        tokens = tokenize_with_spans(text)
        if not tokens:
            return WordPredictResult(words=[], switch_word_index=0, model_used="fallback-heuristic")

        split_idx = self._heuristic_split_index(tokens)

        words = []
        for i, item in enumerate(tokens):
            is_ai = i > split_idx
            label_id = 1 if is_ai else 0
            confidence = self._compute_fallback_confidence(i, split_idx)
            words.append(self._build_word_row(item, label_id, confidence))

        return WordPredictResult(words=words, switch_word_index=split_idx, model_used="fallback-heuristic")

    def predict(self, text: str) -> WordPredictResult:
        if not isinstance(text, str):
            raise TypeError(f"Expected str, got {type(text).__name__}")
        text = text.strip()

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
            base_window=self.BASE_WINDOW,
            base_stride=self.BASE_STRIDE,
            short_window_cap=self.SHORT_WINDOW_CAP,
        )

        rows = []
        for i, token_item in enumerate(tokens):
            vote0 = int(vote_counts[i, 0]) if i < vote_counts.shape[0] else 0
            vote1 = int(vote_counts[i, 1]) if i < vote_counts.shape[0] else 0
            total = max(1, vote0 + vote1)
            conf = max(vote0, vote1) / total
            label_id = int(pred_labels[i]) if i < len(pred_labels) else 0
            rows.append(self._build_word_row(token_item, label_id, conf))

        return WordPredictResult(words=rows, switch_word_index=int(boundary), model_used="deberta-crf")

    # ---- 句子感知推理 ----

    def _sentence_spans(self, text: str, sentence_rows: list[dict[str, Any]]) -> list[tuple[int, int, str]]:
        spans: list[tuple[int, int, str]] = []
        cursor = 0
        for row in sentence_rows:
            sent = str(row.get("text", "")).strip()
            if not sent:
                continue
            start = text.find(sent, cursor)
            if start < 0:
                start = text.find(sent)
            if start < 0:
                start = cursor
            if start < cursor:
                start = cursor
            end = start + len(sent)
            cursor = end
            # V4: 使用静态方法
            label = "AIGT" if self._label_to_id(str(row.get("label", ""))) == 1 else "HWT"
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
                timeout=self.BACKEND_TIMEOUT_SECONDS,
            )
            payload = json.loads(completed.stdout.strip())
            boundary_idx = int(payload.get("boundary_idx", 0))
            logger.debug("External backend returned boundary_idx=%d", boundary_idx)
            return boundary_idx
        except subprocess.TimeoutExpired:
            logger.warning("External boundary backend timed out after %ds", self.BACKEND_TIMEOUT_SECONDS)
            return None
        except subprocess.CalledProcessError as exc:
            logger.warning("External boundary backend failed (exit=%s): %s", exc.returncode, exc.stderr[:200] if exc.stderr else "")
            return None
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            logger.warning("Failed to parse external backend output: %s", exc)
            return None
        except Exception as exc:
            logger.warning("Unexpected error calling external backend: %s", exc)
            return None

    # V4: 抽取 —— 根据句子标签初始化 token 级别的标签和置信度
    def _init_token_labels_from_sentences(
        self,
        tokens: list[dict[str, Any]],
        spans: list[tuple[int, int, str]],
    ) -> tuple[list[int], list[float], list[list[int]]]:
        """根据句子级标签，初始化每个 token 的 label、confidence 及句子→token 索引映射。"""
        token_labels = [0 for _ in tokens]
        token_conf = [self.DEFAULT_TOKEN_CONFIDENCE for _ in tokens]
        sentence_token_indices: list[list[int]] = []

        for start, end, sent_label in spans:
            idxs = [
                i
                for i, tok in enumerate(tokens)
                if tok["start"] >= start and tok["end"] <= end
            ]
            sentence_token_indices.append(idxs)
            label_id = self._label_to_id(sent_label)
            for i in idxs:
                token_labels[i] = label_id
                token_conf[i] = self.SENTENCE_TOKEN_CONFIDENCE

        return token_labels, token_conf, sentence_token_indices

    # V4: 抽取 —— 解析相邻两句之间的局部切换边界
    def _resolve_local_boundary(
        self, local_text: str, combined_idxs: list[int]
    ) -> int:
        """调用外部后端或自身模型，获取局部文本的切换边界并 clamp 到合法范围。"""
        local_boundary = self._call_external_boundary_backend(local_text)
        if local_boundary is None:
            local_res = self.predict(local_text)
            local_boundary = int(local_res.switch_word_index)
        return max(0, min(local_boundary, len(combined_idxs) - 1))

    # V4: 抽取 —— 在句子切换点处精化 token 标签
    def _refine_boundaries_at_switches(
        self,
        text: str,
        spans: list[tuple[int, int, str]],
        sentence_token_indices: list[list[int]],
        token_labels: list[int],
        token_conf: list[float],
    ) -> None:
        """遍历相邻句子，在标签不同的切换点处调用局部检测器精化边界。原地修改 token_labels 和 token_conf。"""
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

            # V4: 使用抽取出的方法
            local_boundary = self._resolve_local_boundary(local_text, combined_idxs)
            boundary_global = combined_idxs[local_boundary]

            left_id = self._label_to_id(left_label)
            right_id = self._label_to_id(right_label)
            for gi in combined_idxs:
                if gi <= boundary_global:
                    token_labels[gi] = left_id
                else:
                    token_labels[gi] = right_id
                token_conf[gi] = self.SWITCH_REFINED_CONFIDENCE

    def predict_with_sentence_switches(self, text: str, sentence_rows: list[dict[str, Any]]) -> WordPredictResult:
        if not isinstance(text, str):
            raise TypeError(f"Expected str, got {type(text).__name__}")
        if not isinstance(sentence_rows, list):
            raise TypeError(f"Expected list for sentence_rows, got {type(sentence_rows).__name__}")

        text = text.strip()
        tokens = tokenize_with_spans(text)
        if not tokens:
            return WordPredictResult(words=[], switch_word_index=0, model_used="switch-aware-empty")

        if not sentence_rows:
            return self.predict(text)

        spans = self._sentence_spans(text, sentence_rows)
        if not spans:
            return self.predict(text)

        # V4: 拆分为两步
        token_labels, token_conf, sentence_token_indices = self._init_token_labels_from_sentences(
            tokens, spans
        )
        self._refine_boundaries_at_switches(
            text, spans, sentence_token_indices, token_labels, token_conf
        )

        rows: list[dict[str, Any]] = []
        for i, tok in enumerate(tokens):
            lid = int(token_labels[i])
            rows.append(self._build_word_row(tok, lid, token_conf[i]))

        switch_idx = self._compute_first_switch_word_index(token_labels)
        return WordPredictResult(
            words=rows,
            switch_word_index=switch_idx,
            model_used="switch-aware-deberta-crf",
        )