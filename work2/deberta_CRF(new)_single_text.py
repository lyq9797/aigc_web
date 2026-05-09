"""
DeBERTa-CRF Sequence Tagger for Single Text Inference.

This module provides a sliding-window inference engine for sequence labeling tasks
using a DeBERTa model combined with a Conditional Random Field (CRF) layer.
It handles long documents by adaptively splitting them into overlapping windows,
performing batch inference, and aggregating predictions via a voting mechanism.
"""

import argparse
import json
import logging
import os
import random
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
from torchcrf import CRF
from transformers import AutoModel, AutoTokenizer, BatchEncoding

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

deberta_HASH = "8ccc9b6f36199bec6961081d44eb72fb3f7353f3"

@dataclass
class InferenceConfig:
    """Configuration parameters for the inference engine."""
    model_name: str = "microsoft/deberta-v3-base"
    best_model_path: str = ""
    max_len: int = 512
    seed: int = 42
    num_labels: int = 2
    base_window: int = 512
    base_stride: int = 384
    short_window_cap: int = 256
    batch_size: int = 8


def set_seed(seed: int) -> None:
    """Sets the random seed for reproducibility across all libraries."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


class DeBERTaCRFTagger(nn.Module):
    """
    A sequence tagging model combining DeBERTa embeddings with a CRF layer.
    """

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

    def forward(
            self,
            input_ids: torch.Tensor,
            attention_mask: torch.Tensor,
            labels: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        """
        Forward pass of the model.

        Args:
            input_ids: Token IDs tensor of shape (batch_size, seq_len).
            attention_mask: Attention mask tensor of shape (batch_size, seq_len).
            labels: Optional ground truth labels for computing CRF loss.

        Returns:
            Loss tensor if labels are provided, otherwise padded predictions tensor.
        """
        outputs = self.deberta(input_ids, attention_mask=attention_mask)
        sequence_output = self.dropout(outputs.last_hidden_state)
        logits = self.classifier(sequence_output)

        if labels is not None:
            mask = attention_mask.bool()
            crf_labels = labels.clone()
            crf_labels[crf_labels == -100] = 0
            return -self.crf(logits, crf_labels, mask=mask, reduction="mean")

        # Decode CRF
        mask = attention_mask.bool()
        predictions = self.crf.decode(logits, mask=mask)

        # Pad predictions to match input sequence length safely without device mismatch
        seq_len = attention_mask.size(1)
        padded_predictions = [
            pred + [0] * (seq_len - len(pred)) for pred in predictions
        ]

        # Return as a standard Python list or tensor on the correct device
        return torch.tensor(padded_predictions, device=input_ids.device)


class InferenceEngine:
    """
    Engine for performing sliding-window inference on long text documents.
    """

    def __init__(
            self,
            model: nn.Module,
            tokenizer: AutoTokenizer,
            device: torch.device,
            config: InferenceConfig
    ):
        self.model = model
        self.tokenizer = tokenizer
        self.device = device
        self.config = config

    def _decode_window_word_predictions_batch(
            self,
            encodings: BatchEncoding,
            pred_ids_batch: List[List[int]]
    ) -> List[List[int]]:
        """Maps sub-word token predictions back to word-level predictions using majority voting."""
        batch_word_preds = []

        for batch_idx in range(len(pred_ids_batch)):
            attention_mask = encodings["attention_mask"][batch_idx].tolist()
            pred_ids = pred_ids_batch[batch_idx][: len(attention_mask)]

            try:
                word_ids = encodings.word_ids(batch_index=batch_idx)
            except Exception:
                word_ids = None

            # Fallback if word_ids is not available
            if word_ids is None:
                special_tokens_mask = encodings["special_tokens_mask"][batch_idx].tolist()
                preds = [
                    int(pred_ids[i]) for i, is_special in enumerate(special_tokens_mask)
                    if attention_mask[i] == 1 and not is_special
                ]
                batch_word_preds.append(preds)
                continue

            # Majority voting for sub-words belonging to the same word
            per_word_votes: Dict[int, List[int]] = {}
            for i, wid in enumerate(word_ids):
                if wid is None or attention_mask[i] == 0:
                    continue
                per_word_votes.setdefault(wid, [0, 0])
                per_word_votes[wid][int(pred_ids[i])] += 1

            word_preds = [1 if votes[1] > votes[0] else 0 for _, votes in sorted(per_word_votes.items())]
            batch_word_preds.append(word_preds)

        return batch_word_preds

    def _build_adaptive_windows(self, doc_len: int) -> List[Tuple[int, int]]:
        """Generates overlapping window indices based on document length."""
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
        """
        Finds the optimal boundary index that minimizes the cost of
        predicting 0s after the boundary and 1s before the boundary.
        """
        n = len(prob_array)
        if n <= 0:
            return 0

        cumsum = np.cumsum(prob_array)
        # Objective: maximize 2 * cumsum[i] - i
        objective = 2 * cumsum - np.arange(n)
        return max(0, min(int(np.argmax(objective)), n - 1))

    def predict(self, words: List[str]) -> Dict[str, Any]:
        """
        Runs inference on a list of words and returns the aggregated predictions.

        Args:
            words: List of words representing the document.

        Returns:
            Dictionary containing boundary index, word labels, and model identifier.
        """
        doc_len = len(words)
        windows = self._build_adaptive_windows(doc_len)
        logger.info(f"Document length: {doc_len}, Number of windows: {len(windows)}")

        pred_1_counts = np.zeros(doc_len, dtype=np.float32)
        coverage_counts = np.zeros(doc_len, dtype=np.float32)

        self.model.eval()

        # Batched sliding window inference
        for i in range(0, len(windows), self.config.batch_size):
            batch_windows = windows[i:i + self.config.batch_size]
            batch_words = [words[start:end] for start, end in batch_windows]

            encodings = self.tokenizer(
                batch_words,
                is_split_into_words=True,
                max_length=self.config.max_len,
                padding="max_length",
                truncation=True,
                return_tensors="pt",
                return_special_tokens_mask=True,
            )
            input_ids = encodings["input_ids"].to(self.device)
            attention_mask = encodings["attention_mask"].to(self.device)

            with torch.no_grad():
                try:
                    predictions = self.model(input_ids, attention_mask)
                except Exception as e:
                    logger.error(f"Batch inference failed: {e}")
                    continue

            pred_ids_batch = predictions.detach().cpu().tolist()
            batch_word_preds = self._decode_window_word_predictions_batch(encodings, pred_ids_batch)

            # Aggregate predictions
            for win_idx, (start, end) in enumerate(batch_windows):
                word_preds = batch_word_preds[win_idx]
                for local_idx, pred in enumerate(word_preds):
                    global_idx = start + local_idx
                    if global_idx < doc_len:
                        coverage_counts[global_idx] += 1.0
                        if int(pred) == 1:
                            pred_1_counts[global_idx] += 1.0

        # Calculate probabilities and find boundary
        safe_coverage = np.where(coverage_counts == 0, 1, coverage_counts)
        prob_array = pred_1_counts / safe_coverage
        boundary = self._decode_boundary_from_scores(prob_array)

        # Clean up GPU memory if applicable
        if self.device.type == "cuda":
            torch.cuda.empty_cache()

        return {
            "boundary_idx": int(boundary),
            "word_labels": [0 if i <= boundary else 1 for i in range(doc_len)],
            "model_used": "work2-deberta-crf-single"
        }


def load_model_and_tokenizer(config: InferenceConfig, device: torch.device) -> Tuple[DeBERTaCRFTagger, AutoTokenizer]:
    """Initializes and loads the model and tokenizer."""
    tokenizer = AutoTokenizer.from_pretrained(config.model_name, revision=deberta_HASH)
    model = DeBERTaCRFTagger(config).to(device)

    if not os.path.exists(config.best_model_path):
        raise FileNotFoundError(f"Model checkpoint not found at {config.best_model_path}")

    logger.info(f"Loading model weights from {config.best_model_path}")
    ckpt = torch.load(config.best_model_path, map_location=device, weights_only=True)
    state_dict = ckpt.get("model_state_dict", ckpt)
    model.load_state_dict(state_dict)

    return model, tokenizer


def main() -> None:
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="DeBERTa-CRF Single Text Inference")
    parser.add_argument("--single_text", type=str, default="", help="Input text to process")
    parser.add_argument("--model_name", type=str, default="microsoft/deberta-v3-base")
    parser.add_argument("--best_model_path", type=str,
                        default=os.path.join(os.path.dirname(__file__), "deberta_CRF(new)_best.pt"))
    parser.add_argument("--max_len", type=int, default=512)
    parser.add_argument("--batch_size", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    empty_response = {"boundary_idx": 0, "word_labels": [], "model_used": "work2-single-empty"}

    text = (args.single_text or "").strip()
    if not text:
        logger.warning("Empty input text provided.")
        print(json.dumps(empty_response, ensure_ascii=False))
        return

    config = InferenceConfig(
        model_name=args.model_name,
        best_model_path=args.best_model_path,
        max_len=args.max_len,
        seed=args.seed,
        batch_size=args.batch_size
    )

    set_seed(config.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Using device: {device}")

    try:
        model, tokenizer = load_model_and_tokenizer(config, device)
    except Exception as e:
        logger.error(f"Failed to initialize model: {e}")
        sys.exit(1)

    words = text.split()
    if not words:
        print(json.dumps(empty_response, ensure_ascii=False))
        return

    engine = InferenceEngine(model, tokenizer, device, config)
    result = engine.predict(words)

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()