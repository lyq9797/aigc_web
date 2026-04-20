import argparse
import json
import logging
import os
import random
import sys
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any

import numpy as np
import torch
import torch.nn as nn
from torchcrf import CRF
from transformers import AutoModel, AutoTokenizer, BatchEncoding

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class InferenceConfig:
    model_name: str = "microsoft/deberta-v3-base"
    best_model_path: str = ""
    max_len: int = 512
    seed: int = 42
    num_labels: int = 2
    base_window: int = 512
    base_stride: int = 384
    short_window_cap: int = 256


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


class DeBERTaCRFTagger(nn.Module):
    def __init__(self, config: InferenceConfig, dropout_rate: float = 0.1):
        super().__init__()
        self.num_labels = config.num_labels
        self.deberta = AutoModel.from_pretrained(config.model_name)
        self.dropout = nn.Dropout(dropout_rate)
        hidden_size = self.deberta.config.hidden_size
        self.classifier = nn.Linear(hidden_size, config.num_labels)
        nn.init.xavier_uniform_(self.classifier.weight)
        nn.init.constant_(self.classifier.bias, 0)
        self.crf = CRF(config.num_labels, batch_first=True)

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor,
                labels: torch.Tensor = None) -> torch.Tensor:
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


class InferenceEngine:
    def __init__(self, model: nn.Module, tokenizer: AutoTokenizer, device: torch.device, config: InferenceConfig):
        self.model = model
        self.tokenizer = tokenizer
        self.device = device
        self.config = config

    def _decode_window_word_predictions(self, encoding: BatchEncoding, pred_ids: List[int]) -> List[int]:
        attention_mask = encoding["attention_mask"][0].tolist()
        pred_ids = pred_ids[: len(attention_mask)]

        try:
            word_ids = encoding.word_ids(batch_index=0)
        except Exception:
            word_ids = None

        if word_ids is None:
            special_tokens_mask = encoding["special_tokens_mask"][0].tolist()
            return [int(pred_ids[i]) for i, is_special in enumerate(special_tokens_mask)
                    if attention_mask[i] == 1 and not is_special]

        per_word_votes: Dict[int, List[int]] = {}
        for i, wid in enumerate(word_ids):
            if wid is None or attention_mask[i] == 0:
                continue
            per_word_votes.setdefault(wid, [0, 0])
            per_word_votes[wid][int(pred_ids[i])] += 1

        return [1 if votes[1] > votes[0] else 0 for _, votes in sorted(per_word_votes.items())]

    def _build_adaptive_windows(self, doc_len: int) -> List[Tuple[int, int]]:
        if doc_len <= 0:
            return [(0, 0)]

        if doc_len > self.config.base_window:
            win_size, stride = self.config.base_window, self.config.base_stride
        else:
            win_size = min(self.config.short_window_cap, doc_len)
            if win_size >= doc_len and doc_len > 2:
                win_size = max(2, int(np.ceil(doc_len * 0.75)))
            stride = max(1, win_size // 2)

        if win_size >= doc_len:
            return [(0, doc_len)]

        starts = list(range(0, doc_len - win_size + 1, stride))
        if starts[-1] != doc_len - win_size:
            starts.append(doc_len - win_size)
        if len(starts) < 2 and doc_len > win_size:
            starts.append((doc_len - win_size) // 2)

        return [(s, s + win_size) for s in sorted(set(starts))]

    def _decode_boundary_from_scores(self, prob_array: np.ndarray) -> int:
        n = len(prob_array)
        if n <= 0:
            return 0
        cumsum = np.cumsum(prob_array)
        objective = 2 * cumsum - np.arange(n)
        return max(0, min(int(np.argmax(objective)), n - 1))

    def predict(self, words: List[str]) -> Dict[str, Any]:
        doc_len = len(words)
        windows = self._build_adaptive_windows(doc_len)
        logger.info(f"Document length: {doc_len}, Windows: {len(windows)}")

        pred_1_counts = np.zeros(doc_len, dtype=np.float32)
        coverage_counts = np.zeros(doc_len, dtype=np.float32)

        self.model.eval()
        with torch.no_grad():
            for start, end in windows:
                encoding = self.tokenizer(
                    words[start:end], is_split_into_words=True, max_length=self.config.max_len,
                    padding="max_length", truncation=True, return_tensors="pt", return_special_tokens_mask=True,
                )
                input_ids = encoding["input_ids"].to(self.device)
                attention_mask = encoding["attention_mask"].to(self.device)

                try:
                    predictions = self.model(input_ids, attention_mask)
                except Exception as e:
                    logger.error(f"Inference failed [{start}:{end}]: {e}")
                    continue

                pred_ids = predictions[0].detach().cpu().tolist()
                word_preds = self._decode_window_word_predictions(encoding, pred_ids)

                for local_idx, pred in enumerate(word_preds):
                    global_idx = start + local_idx
                    if global_idx < doc_len:
                        coverage_counts[global_idx] += 1.0
                        if int(pred) == 1:
                            pred_1_counts[global_idx] += 1.0

        safe_coverage = np.where(coverage_counts == 0, 1, coverage_counts)
        boundary = self._decode_boundary_from_scores(pred_1_counts / safe_coverage)

        return {
            "boundary_idx": int(boundary),
            "word_labels": [0 if i <= boundary else 1 for i in range(doc_len)],
            "model_used": "work2-deberta-crf-single"
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--single_text", type=str, default="")
    parser.add_argument("--model_name", type=str, default="microsoft/deberta-v3-base")
    parser.add_argument("--best_model_path", type=str,
                        default=os.path.join(os.path.dirname(__file__), "deberta_CRF(new)_best.pt"))
    parser.add_argument("--max_len", type=int, default=512)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    text = (args.single_text or "").strip()
    if not text:
        print(
            json.dumps({"boundary_idx": 0, "word_labels": [], "model_used": "work2-single-empty"}, ensure_ascii=False))
        return

    config = InferenceConfig(
        model_name=args.model_name,
        best_model_path=args.best_model_path,
        max_len=args.max_len,
        seed=args.seed
    )

    set_seed(config.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Using device: {device}")

    tokenizer = AutoTokenizer.from_pretrained(config.model_name)
    model = DeBERTaCRFTagger(config).to(device)

    try:
        ckpt = torch.load(config.best_model_path, map_location=device, weights_only=False)
        model.load_state_dict(ckpt.get("model_state_dict", ckpt))
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        sys.exit(1)

    words = text.split()
    if not words:
        print(
            json.dumps({"boundary_idx": 0, "word_labels": [], "model_used": "work2-single-empty"}, ensure_ascii=False))
        return

    engine = InferenceEngine(model, tokenizer, device, config)
    print(json.dumps(engine.predict(words), ensure_ascii=False))


if __name__ == "__main__":
    main()