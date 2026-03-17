# word_model_runtime.py — Version 2
# 改动：增加 logging、输入校验、具体异常捕获

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from torchcrf import CRF
from transformers import AutoModel

logger = logging.getLogger(__name__)

# ---------- 常量定义 ----------
LABEL_NEGATIVE = 0
LABEL_POSITIVE = 1
NUM_BINARY_LABELS = 2
IGNORE_INDEX = -100
DEFAULT_DROPOUT = 0.1
PAD_LABEL = 0


class DeBERTaCRFTagger(nn.Module):
    def __init__(self, model_name: str, num_labels: int, dropout_rate: float = DEFAULT_DROPOUT):
        super().__init__()
        if num_labels <= 0:
            raise ValueError(f"num_labels must be positive, got {num_labels}")
        if not 0.0 <= dropout_rate < 1.0:
            raise ValueError(f"dropout_rate must be in [0, 1), got {dropout_rate}")

        self.num_labels = num_labels
        self.deberta = AutoModel.from_pretrained(model_name)
        self.dropout = nn.Dropout(dropout_rate)
        hidden_size: int = self.deberta.config.hidden_size
        self.classifier = nn.Linear(hidden_size, num_labels)
        nn.init.xavier_uniform_(self.classifier.weight)
        nn.init.constant_(self.classifier.bias, 0)
        self.crf = CRF(num_labels, batch_first=True)
        logger.info("DeBERTaCRFTagger initialized: model=%s, labels=%d, dropout=%.2f",
                     model_name, num_labels, dropout_rate)

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        labels: torch.Tensor | None = None,
    ) -> torch.Tensor:
        outputs = self.deberta(input_ids, attention_mask=attention_mask)
        sequence_output = self.dropout(outputs.last_hidden_state)
        logits = self.classifier(sequence_output)

        if labels is not None:
            mask = attention_mask.bool()
            crf_labels = labels.clone()
            crf_labels[crf_labels == IGNORE_INDEX] = PAD_LABEL
            loss = -self.crf(logits, crf_labels, mask=mask, reduction="mean")
            return loss

        mask = attention_mask.bool()
        predictions = self.crf.decode(logits, mask=mask)
        padded_predictions: list[list[int]] = []
        for pred in predictions:
            pad_len = attention_mask.size(1) - len(pred)
            padded_predictions.append(pred + [PAD_LABEL] * pad_len)
        return torch.tensor(padded_predictions, device=input_ids.device)


def decode_window_word_predictions(encoding: Any, pred_ids: list[int]) -> list[int]:
    if not pred_ids:
        logger.warning("decode_window_word_predictions received empty pred_ids")
        return []

    attention_mask: list[int] = encoding["attention_mask"][0].tolist()
    pred_ids = pred_ids[: len(attention_mask)]

    word_ids = None
    try:
        word_ids = encoding.word_ids(batch_index=0)
    except (AttributeError, TypeError, IndexError) as exc:
        logger.debug("word_ids() unavailable, falling back to special_tokens_mask: %s", exc)

    if word_ids is None:
        special_tokens_mask: list[int] = encoding["special_tokens_mask"][0].tolist()
        word_level_preds: list[int] = []
        for i, is_special in enumerate(special_tokens_mask):
            if attention_mask[i] == 1 and not is_special:
                word_level_preds.append(int(pred_ids[i]))
        return word_level_preds

    per_word_votes: dict[int, list[int]] = {}
    for i, wid in enumerate(word_ids):
        if wid is None or attention_mask[i] == 0:
            continue
        per_word_votes.setdefault(wid, [0, 0])
        label = int(pred_ids[i])
        if 0 <= label < NUM_BINARY_LABELS:
            per_word_votes[wid][label] += 1
        else:
            logger.warning("Unexpected label %d at token index %d, skipping", label, i)

    word_level_preds = []
    for wid in sorted(per_word_votes.keys()):
        votes = per_word_votes[wid]
        word_level_preds.append(LABEL_POSITIVE if votes[LABEL_POSITIVE] > votes[LABEL_NEGATIVE] else LABEL_NEGATIVE)
    return word_level_preds


def build_adaptive_windows(
    doc_len: int,
    base_window: int = 512,
    base_stride: int = 256,
    short_window_cap: int = 256,
) -> list[tuple[int, int]]:
    if doc_len < 0:
        raise ValueError(f"doc_len must be non-negative, got {doc_len}")
    if base_window <= 0 or base_stride <= 0:
        raise ValueError("base_window and base_stride must be positive")
    if base_stride >= base_window:
        logger.warning("base_stride (%d) >= base_window (%d), windows may not cover full document",
                        base_stride, base_window)

    if doc_len == 0:
        return [(0, 0)]

    if doc_len > base_window:
        win_size = base_window
        stride = base_stride
    else:
        win_size = min(short_window_cap, doc_len)
        if win_size >= doc_len and doc_len > 2:
            win_size = max(2, int(np.ceil(doc_len * 0.75)))
        stride = max(1, win_size // 2)

    if win_size >= doc_len:
        return [(0, doc_len)]

    starts = list(range(0, doc_len - win_size + 1, stride))
    last_start = doc_len - win_size
    if starts[-1] != last_start:
        starts.append(last_start)

    if len(starts) < 2 and doc_len > win_size:
        mid_start = (doc_len - win_size) // 2
        starts.append(mid_start)
        starts = sorted(set(starts))

    return [(s, s + win_size) for s in starts]


def decode_boundary_from_scores(score_sum: np.ndarray) -> int:
    n = len(score_sum)
    if n <= 0:
        return 0

    prefix_neg = np.cumsum(-score_sum)
    prefix_pos = np.cumsum(score_sum)
    total_pos = prefix_pos[-1]
    objective = prefix_neg + (total_pos - prefix_pos)
    best_boundary: int = int(np.argmax(objective))
    return max(0, min(best_boundary, n - 1))


def infer_document_with_sliding_windows(
    model: DeBERTaCRFTagger,
    words: list[str],
    tokenizer: Any,
    max_len: int,
    device: Any,
    base_window: int = 512,
    base_stride: int = 256,
    short_window_cap: int = 256,
) -> tuple[list[int], int, np.ndarray]:
    if not words:
        logger.warning("infer_document_with_sliding_windows received empty word list")
        return [], 0, np.zeros(0, dtype=np.int32)
    if max_len <= 0:
        raise ValueError(f"max_len must be positive, got {max_len}")

    doc_len = len(words)
    windows = build_adaptive_windows(
        doc_len,
        base_window=base_window,
        base_stride=base_stride,
        short_window_cap=short_window_cap,
    )
    logger.info("Inference: doc_len=%d, num_windows=%d", doc_len, len(windows))

    vote_counts = np.zeros((doc_len, NUM_BINARY_LABELS), dtype=np.int32)
    score_sum = np.zeros(doc_len, dtype=np.float32)

    with torch.no_grad():
        for win_idx, (start, end) in enumerate(windows):
            window_words = words[start:end]
            encoding = tokenizer(
                window_words,
                is_split_into_words=True,
                max_length=max_len,
                padding="max_length",
                truncation=True,
                return_tensors="pt",
                return_special_tokens_mask=True,
            )
            input_ids = encoding["input_ids"].to(device)
            attention_mask = encoding["attention_mask"].to(device)
            predictions = model(input_ids, attention_mask)
            pred_ids: list[int] = predictions[0].detach().cpu().tolist()

            word_preds = decode_window_word_predictions(encoding, pred_ids)
            for local_idx, pred in enumerate(word_preds):
                global_idx = start + local_idx
                if global_idx < doc_len:
                    pred_i = int(pred)
                    vote_counts[global_idx, pred_i] += 1
                    score_sum[global_idx] += 1.0 if pred_i == LABEL_POSITIVE else -1.0

            logger.debug("Window %d [%d:%d] processed, %d word-level predictions",
                          win_idx, start, end, len(word_preds))

    boundary = decode_boundary_from_scores(score_sum)
    pred_word_labels = [LABEL_NEGATIVE if i <= boundary else LABEL_POSITIVE for i in range(doc_len)]
    logger.info("Inference complete: boundary=%d, doc_len=%d", boundary, doc_len)
    return pred_word_labels, boundary, vote_counts