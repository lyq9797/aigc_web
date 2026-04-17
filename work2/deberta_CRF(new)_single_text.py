import argparse
import json
import logging
import os
import random
import sys
from typing import List, Tuple, Dict, Any

import numpy as np
import torch
import torch.nn as nn
from torchcrf import CRF
from transformers import AutoModel, AutoTokenizer, BatchEncoding

NUM_LABELS = 2
DEFAULT_MAX_LEN = 512
BASE_WINDOW = 512
BASE_STRIDE = 384
SHORT_WINDOW_CAP = 256

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


class DeBERTaCRFTagger(nn.Module):
    def __init__(self, model_name: str, num_labels: int = NUM_LABELS, dropout_rate: float = 0.1):
        super().__init__()
        self.num_labels = num_labels
        self.deberta = AutoModel.from_pretrained(model_name)
        self.dropout = nn.Dropout(dropout_rate)
        hidden_size = self.deberta.config.hidden_size
        self.classifier = nn.Linear(hidden_size, num_labels)
        nn.init.xavier_uniform_(self.classifier.weight)
        nn.init.constant_(self.classifier.bias, 0)
        self.crf = CRF(num_labels, batch_first=True)

    def forward(self, input_ids, attention_mask, labels=None):
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
    def __init__(self, model: nn.Module, tokenizer: AutoTokenizer, device: torch.device,
                 max_len: int = DEFAULT_MAX_LEN):
        self.model = model
        self.tokenizer = tokenizer
        self.device = device
        self.max_len = max_len

    def _decode_window_word_predictions(self, encoding: BatchEncoding, pred_ids: List[int]) -> List[int]:
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

        per_word_votes = {}
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

    def _build_adaptive_windows(self, doc_len: int) -> List[Tuple[int, int]]:
        if doc_len <= 0:
            return [(0, 0)]

        if doc_len > BASE_WINDOW:
            win_size = BASE_WINDOW
            stride = BASE_STRIDE
        else:
            win_size = min(SHORT_WINDOW_CAP, doc_len)
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

    def _decode_boundary_from_scores(self, prob_array: np.ndarray) -> int:
        n = len(prob_array)
        if n <= 0:
            return 0
        cumsum = np.cumsum(prob_array)
        objective = 2 * cumsum - np.arange(n)
        best_boundary = int(np.argmax(objective))
        return max(0, min(best_boundary, n - 1))

    def predict(self, words: List[str]) -> Dict[str, Any]:
        doc_len = len(words)
        windows = self._build_adaptive_windows(doc_len)
        logger.info(f"Document length: {doc_len}, Number of windows: {len(windows)}")

        pred_1_counts = np.zeros(doc_len, dtype=np.float32)
        coverage_counts = np.zeros(doc_len, dtype=np.float32)

        self.model.eval()
        with torch.no_grad():
            for start, end in windows:
                window_words = words[start:end]
                encoding = self.tokenizer(
                    window_words,
                    is_split_into_words=True,
                    max_length=self.max_len,
                    padding="max_length",
                    truncation=True,
                    return_tensors="pt",
                    return_special_tokens_mask=True,
                )
                input_ids = encoding["input_ids"].to(self.device)
                attention_mask = encoding["attention_mask"].to(self.device)

                try:
                    predictions = self.model(input_ids, attention_mask)
                except Exception as e:
                    logger.error(f"Model inference failed for window [{start}:{end}]: {e}")
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
        prob_array = pred_1_counts / safe_coverage

        boundary = self._decode_boundary_from_scores(prob_array)
        pred_word_labels = [0 if i <= boundary else 1 for i in range(doc_len)]

        return {
            "boundary_idx": int(boundary),
            "word_labels": [int(x) for x in pred_word_labels],
            "model_used": "work2-deberta-crf-single"
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--single_text", type=str, default="")
    parser.add_argument("--output_json", action="store_true")
    parser.add_argument("--model_name", type=str, default="microsoft/deberta-v3-base")
    parser.add_argument("--best_model_path", type=str,
                        default=os.path.join(os.path.dirname(__file__), "deberta_CRF(new)_best.pt"))
    parser.add_argument("--max_len", type=int, default=DEFAULT_MAX_LEN)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    text = (args.single_text or "").strip()
    if not text:
        logger.warning("Empty input text provided.")
        print(
            json.dumps({"boundary_idx": 0, "word_labels": [], "model_used": "work2-single-empty"}, ensure_ascii=False))
        return

    set_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Using device: {device}")

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    model = DeBERTaCRFTagger(args.model_name, NUM_LABELS).to(device)

    try:
        logger.info(f"Loading model from {args.best_model_path}")
        ckpt = torch.load(args.best_model_path, map_location=device, weights_only=False)
        state = ckpt.get("model_state_dict", ckpt)
        model.load_state_dict(state)
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        sys.exit(1)

    words = text.split()
    if not words:
        print(
            json.dumps({"boundary_idx": 0, "word_labels": [], "model_used": "work2-single-empty"}, ensure_ascii=False))
        return

    engine = InferenceEngine(model, tokenizer, device, args.max_len)
    result = engine.predict(words)

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()