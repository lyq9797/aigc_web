from __future__ import annotations

from typing import Any

import numpy as np
import torch
import torch.nn as nn
from torchcrf import CRF
from transformers import AutoModel


class DeBERTaCRFTagger(nn.Module):
    def __init__(self, model_name: str, num_labels: int, dropout_rate: float = 0.1):
        super().__init__()
        self.num_labels = num_labels
        self.deberta = AutoModel.from_pretrained(model_name, revision="8ccc9b6f36199bec6961081d44eb72fb3f7353f3")
        self.dropout = nn.Dropout(dropout_rate)
        hidden_size = self.deberta.config.hidden_size
        self.classifier = nn.Linear(hidden_size, num_labels)
        nn.init.xavier_uniform_(self.classifier.weight)
        nn.init.constant_(self.classifier.bias, 0)
        self.crf = CRF(num_labels, batch_first=True)

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor, labels: torch.Tensor | None = None):
        outputs = self.deberta(input_ids, attention_mask=attention_mask)
        sequence_output = self.dropout(outputs.last_hidden_state)
        logits = self.classifier(sequence_output)

        if labels is not None:
            mask = attention_mask.bool()
            crf_labels = labels.clone()
            crf_labels[crf_labels == -100] = 0
            loss = -self.crf(logits, crf_labels, mask=mask, reduction="mean")
            return loss

        mask = attention_mask.bool()
        predictions = self.crf.decode(logits, mask=mask)
        padded_predictions = []
        for pred in predictions:
            pad_len = attention_mask.size(1) - len(pred)
            padded_predictions.append(pred + [0] * pad_len)
        return torch.tensor(padded_predictions, device=input_ids.device)


def decode_window_word_predictions(encoding: Any, pred_ids: list[int]) -> list[int]:
    attention_mask = encoding["attention_mask"][0].tolist()
    pred_ids = pred_ids[: len(attention_mask)]

    try:
        word_ids = encoding.word_ids(batch_index=0)
    except Exception:
        word_ids = None

    if word_ids is None:
        special_tokens_mask = encoding["special_tokens_mask"][0].tolist()
        word_level_preds = []
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
        per_word_votes[wid][label] += 1

    word_level_preds = []
    for wid in sorted(per_word_votes.keys()):
        votes = per_word_votes[wid]
        word_level_preds.append(1 if votes[1] > votes[0] else 0)
    return word_level_preds


def build_adaptive_windows(doc_len: int, base_window: int = 512, base_stride: int = 256, short_window_cap: int = 256) -> list[tuple[int, int]]:
    if doc_len <= 0:
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
    best_boundary = int(np.argmax(objective))
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
    doc_len = len(words)
    windows = build_adaptive_windows(
        doc_len,
        base_window=base_window,
        base_stride=base_stride,
        short_window_cap=short_window_cap,
    )

    vote_counts = np.zeros((doc_len, 2), dtype=np.int32)
    score_sum = np.zeros(doc_len, dtype=np.float32)

    with torch.no_grad():
        for start, end in windows:
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
            pred_ids = predictions[0].detach().cpu().tolist()

            word_preds = decode_window_word_predictions(encoding, pred_ids)
            for local_idx, pred in enumerate(word_preds):
                global_idx = start + local_idx
                if global_idx < doc_len:
                    pred_i = int(pred)
                    vote_counts[global_idx, pred_i] += 1
                    score_sum[global_idx] += 1.0 if pred_i == 1 else -1.0

    boundary = decode_boundary_from_scores(score_sum)
    pred_word_labels = [0 if i <= boundary else 1 for i in range(doc_len)]
    return pred_word_labels, boundary, vote_counts
