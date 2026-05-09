"""
AI Generated Text (AIGT) Detection Pipeline

This module provides a pipeline to detect AI-generated text at the sentence level.
It utilizes a GPT-2 based perplexity calculator and a custom DeBERTa-based sentence head model
with a sliding window and confidence-weighted voting mechanism.

Author: Graduate Research Team
Version: 7.0 (Production Ready)
"""

import argparse
import json
import re
import string
import logging
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any
import torch
import transformers
import numpy as np
from transformers.models.gpt2.tokenization_gpt2 import bytes_to_unicode

GPT2_HASH = "32b71b12589c2f8d625668d2335a01cac3249519"

# Configure logging for production environment
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("AIGT_Detector")


def get_compute_device() -> torch.device:
    """Determine the optimal compute device (CUDA or CPU)."""
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


@dataclass(frozen=True)
class PipelineConfig:
    """Immutable configuration parameters for the detection pipeline."""
    gpt2_model_path: str = r'D:\wy\gpt2-xl'
    head_model_folder: str = r'F:\wy\work1\windows_log\windows_webuse'
    head_model_name: str = 'epoch-last.pkl'
    window_size: int = 3
    window_step: int = 1
    max_seq_len: int = 1024
    feature_pad_len: int = 512
    ai_threshold: float = 0.5


class GPT2PerplexityCalculator:
    """
    Calculates token-level and sentence-level perplexity using GPT-2.
    Maps byte-level BPE tokens back to word/sentence boundaries.
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.device = get_compute_device()
        logger.info(f"Initializing GPT-2 Perplexity Calculator on {self.device}")

        try:
            self.tokenizer = transformers.AutoTokenizer.from_pretrained(config.gpt2_model_path, revision=GPT2_HASH)
            self.model = transformers.AutoModelForCausalLM.from_pretrained(config.gpt2_model_path, revision=GPT2_HASH)
            self.tokenizer.pad_token_id = self.tokenizer.eos_token_id
            self.model.eval().to(self.device)
        except Exception as e:
            logger.critical(f"Failed to initialize GPT-2 model: {e}")
            raise RuntimeError("GPT-2 model initialization failed.") from e

        self.byte_encoder = bytes_to_unicode()
        self.byte_decoder = {v: k for k, v in self.byte_encoder.items()}

    @torch.inference_mode()
    def calculate_perplexity(self, text: str) -> Tuple[float, int, List[float]]:
        """
        Compute perplexity metrics for a given text.

        Args:
            text: Input text string.

        Returns:
            Tuple containing (mean_sentence_loss, begin_word_index, token_level_losses).
        """
        if not text.strip():
            return 0.0, 0, []

        try:
            encoded = self.tokenizer(
                text, return_tensors="pt", truncation=True, max_length=self.config.max_seq_len
            ).to(self.device)
            input_ids = encoded.input_ids

            # Map bytes to sentence indices for aggregation
            byte_to_word_idx = []
            for s_idx, part in enumerate(split_sentences(text)):
                byte_to_word_idx.extend([s_idx] * len(part.encode("utf-8")))

            outputs = self.model(input_ids=input_ids, labels=input_ids)

            logits = outputs.logits.squeeze(0) if outputs.logits.dim() == 3 else outputs.logits
            shift_logits = logits[:-1, :].contiguous()
            shift_labels = input_ids.squeeze()[1:].contiguous()

            token_losses = torch.nn.CrossEntropyLoss(reduction="none")(shift_logits, shift_labels).cpu().tolist()

            sub_tokens = [self.tokenizer._convert_id_to_token(tid) for tid in input_ids.squeeze()]
            if not sub_tokens:
                return 0.0, 0, []

            # Map token losses to byte losses
            byte_losses = [0.0] * len(sub_tokens[0])
            for t_idx, st in enumerate(sub_tokens[1:]):
                byte_losses.extend([token_losses[t_idx]] * len(st))

            # Aggregate byte losses back to word/sentence level
            token_level_losses, start = [], 0
            while start < len(byte_to_word_idx) and start < len(byte_losses):
                end = start + 1
                while end < len(byte_to_word_idx) and byte_to_word_idx[end] == byte_to_word_idx[start]:
                    end += 1
                if end > len(byte_losses):
                    break
                token_level_losses.append(float(np.mean(byte_losses[start:end])))
                start = end

            begin_word_idx = byte_to_word_idx[len(sub_tokens[0]) - 1] + 1 if sub_tokens[0] else 0
            return float(np.mean(token_losses)), begin_word_idx, token_level_losses

        except torch.cuda.OutOfMemoryError:
            logger.error("CUDA Out of Memory during PPL calculation.")
            return 0.0, 0, []
        except Exception as e:
            logger.warning(f"Unexpected error in PPL calculation: {e}")
            return 0.0, 0, []


def split_sentences(text: str) -> List[str]:
    """Split text into sentences using regex, supporting common CN/EN punctuations."""
    text = (text or "").strip()
    if not text:
        return []
    chunks = re.split(r"(?<=[。！？.!?；;：:])\s+", text)
    return [c.strip() for c in chunks if c.strip()] or [text]


def is_trivial_sentence(sentence: str) -> bool:
    """Check if a sentence is too short or trivial (e.g., only punctuation/numbers)."""
    s = sentence.replace(" ", "")
    if not s or all(c in string.punctuation for c in s) or s.isdigit():
        return True
    if len(s) == 1 and s.isalpha():
        return True
    return len(s.split()) <= 1


def pad_list(input_list: List[float], target_len: int) -> List[float]:
    """Pad or truncate a list to a target length."""
    if len(input_list) < target_len:
        return input_list + [0.0] * (target_len - len(input_list))
    return input_list[:target_len]


def calc_tail_difference(list1: List[float], list2: List[float]) -> List[float]:
    """Calculate absolute difference between the tail of list1 and list2."""
    if not list2:
        return []
    if len(list1) < len(list2):
        return [0.0] * len(list2)
    return [abs(a - b) for a, b in zip(list1[-len(list2):], list2)]


class SingleSentencePredictor:
    """
    Main predictor class that combines GPT-2 PPL features with a DeBERTa sentence head.
    Uses a sliding window approach with confidence-weighted voting.
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.device = get_compute_device()
        self.ppl_calc = GPT2PerplexityCalculator(config)

        model_path = Path(config.head_model_folder) / config.head_model_name
        if not model_path.exists():
            raise FileNotFoundError(f"Sentence Head model not found at {model_path}")

        logger.info(f"Loading Sentence Head model from {model_path}")
        try:
            self.head_model = torch.load(str(model_path), map_location=self.device, weights_only=True )
        except TypeError:
            # Fallback for older PyTorch versions
            self.head_model = torch.load(str(model_path), map_location=self.device, weights_only=True)

        if not hasattr(self.head_model, 'extract_deberta_PPL'):
            raise AttributeError("Loaded model missing required method 'extract_deberta_PPL'")
        self.head_model.eval()

    @torch.inference_mode()
    def _extract_features(self, sentences: List[str]) -> torch.Tensor:
        """Extract PPL difference features for a window of sentences."""
        s1 = sentences[0] if len(sentences) > 0 else ""
        s2 = sentences[1] if len(sentences) > 1 else s1
        s3 = sentences[2] if len(sentences) > 2 else s2

        # Handle trivial sentences by duplicating content to avoid empty context
        s1 = s1 + " " + s1 if is_trivial_sentence(s1) else s1
        s2 = s2 + " " + s2 if is_trivial_sentence(s2) else s2
        s3 = s3 + " " + s3 if is_trivial_sentence(s3) else s3

        _, _, loss3 = self.ppl_calc.calculate_perplexity(s3)
        _, _, loss123 = self.ppl_calc.calculate_perplexity(f"{s1} {s2} {s3}")

        diff = calc_tail_difference(loss123, loss3)
        return torch.tensor(pad_list(diff, self.config.feature_pad_len), dtype=torch.float32)

    def predict_scores(self, sentences: List[str]) -> List[float]:
        """
        Predict AI-generation scores for a list of sentences.

        Args:
            sentences: List of sentence strings.

        Returns:
            List of float scores between 0.0 and 1.0.
        """
        if not sentences:
            return []

        votes = [[] for _ in range(len(sentences))]

        # Sliding window inference
        for start in range(0, max(1, len(sentences) - self.config.window_size + 1), self.config.window_step):
            window = sentences[start: start + self.config.window_size]
            feat = self._extract_features(window)
            deberta_feat = self.head_model.extract_deberta_PPL(" ".join(window), feat, 1)
            score = torch.sigmoid(self.head_model(deberta_feat)).item()

            for i in range(start, min(start + self.config.window_size, len(sentences))):
                votes[i].append(score)

        # Confidence-weighted aggregation
        final_scores = []
        for v in votes:
            if not v:
                final_scores.append(0.5)
                continue
            if len(v) <= 2:
                final_scores.append(sum(v) / len(v))
                continue

            # Higher weight for predictions further from 0.5 (higher confidence)
            weights = [abs(p - 0.5) * 2 for p in v]
            total_w = sum(weights)
            if total_w == 0:
                final_scores.append(sum(v) / len(v))
            else:
                norm_w = [w / total_w for w in weights]
                final_scores.append(sum(p * w for p, w in zip(v, norm_w)))

        return final_scores


def find_switch_index(results: List[Dict[str, Any]], threshold: float) -> int:
    """Identify the first sentence index where AI generation is detected."""
    for idx, row in enumerate(results):
        if row["confidence"] >= threshold:
            return idx
    return len(results)


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="AI Generated Text Detection Pipeline")
    parser.add_argument("--single_text", type=str, default="title: Rodrigo Duterte...")
    parser.add_argument("--head_folder", type=str, default=r"F:\wy\work1\windows_log\windows_webuse")
    parser.add_argument("--head_model", type=str, default="epoch-last.pkl")
    parser.add_argument("--window_size", type=int, default=3, help="Sliding window size")
    parser.add_argument("--window_step", type=int, default=1, help="Sliding window step")
    return parser.parse_args()


def main() -> None:
    """Main entry point for the detection pipeline."""
    args = parse_arguments()
    config = PipelineConfig(
        head_model_folder=args.head_folder,
        head_model_name=args.head_model,
        window_size=args.window_size,
        window_step=args.window_step
    )

    text = (args.single_text or "").strip()
    if not text:
        print(json.dumps({"sentences": [], "switch_sentence_index": 0, "model_used": "empty"}))
        return

    try:
        predictor = SingleSentencePredictor(config)
        sents = split_sentences(text)
        scores = predictor.predict_scores(sents)

        rows = []
        for idx, (sent, score) in enumerate(zip(sents, scores)):
            label = "AIGT" if score >= config.ai_threshold else "HWT"
            rows.append({
                "index": idx,
                "text": sent,
                "label": label,
                "confidence": round(score, 4),
                "ai_ratio": round(score, 4)
            })

        switch_idx = find_switch_index(rows, config.ai_threshold)
        output_payload = {
            "sentences": rows,
            "switch_sentence_index": switch_idx,
            "model_used": "v7-production"
        }
        print(json.dumps(output_payload, ensure_ascii=False, indent=2))

    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()