import argparse
import json
import re
import string
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple
import torch
import transformers
import numpy as np
from transformers.models.gpt2.tokenization_gpt2 import bytes_to_unicode

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_device():
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


@dataclass
class AppConfig:
    gpt2_model_path: str = r'D:\wy\gpt2-xl'
    head_model_folder: str = r'F:\wy\work1\windows_log\windows_webuse'
    head_model_name: str = 'epoch-last.pkl'
    window_size: int = 3
    window_step: int = 1
    max_seq_len: int = 1024
    feature_pad_len: int = 512
    ai_threshold: float = 0.5


class GPT2PerplexityCalculator:
    def __init__(self, config: AppConfig):
        self.config = config
        self.device = get_device()
        logger.info(f"Loading GPT-2 model to {self.device}")

        self.tokenizer = transformers.AutoTokenizer.from_pretrained(config.gpt2_model_path)
        self.model = transformers.AutoModelForCausalLM.from_pretrained(config.gpt2_model_path)
        self.tokenizer.pad_token_id = self.tokenizer.eos_token_id
        self.model.eval().to(self.device)

        self.byte_encoder = bytes_to_unicode()
        self.byte_decoder = {v: k for k, v in self.byte_encoder.items()}

    def calculate_perplexity(self, text: str) -> Tuple[float, int, List[float]]:
        if not text.strip(): return 0.0, 0, []

        encoded = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=self.config.max_seq_len).to(
            self.device)
        input_ids = encoded.input_ids

        byte_to_word_idx = []
        for s_idx, part in enumerate(split_sentences(text)):
            byte_to_word_idx.extend([s_idx] * len(part.encode("utf-8")))

        with torch.no_grad():
            outputs = self.model(input_ids=input_ids, labels=input_ids)

        logits = outputs.logits.squeeze(0) if outputs.logits.dim() == 3 else outputs.logits
        shift_logits = logits[:-1, :].contiguous()
        shift_labels = input_ids.squeeze()[1:].contiguous()

        token_losses = torch.nn.CrossEntropyLoss(reduction="none")(shift_logits, shift_labels).cpu().tolist()

        sub_tokens = [self.tokenizer._convert_id_to_token(tid) for tid in input_ids.squeeze()]
        if not sub_tokens: return 0.0, 0, []

        byte_losses = [0.0] * len(sub_tokens[0])
        for t_idx, st in enumerate(sub_tokens[1:]):
            byte_losses.extend([token_losses[t_idx]] * len(st))

        token_level_losses, start = [], 0
        while start < len(byte_to_word_idx) and start < len(byte_losses):
            end = start + 1
            while end < len(byte_to_word_idx) and byte_to_word_idx[end] == byte_to_word_idx[start]: end += 1
            if end > len(byte_losses): break
            token_level_losses.append(float(np.mean(byte_losses[start:end])))
            start = end

        begin_word_idx = byte_to_word_idx[len(sub_tokens[0]) - 1] + 1 if sub_tokens[0] else 0
        return float(np.mean(token_losses)), begin_word_idx, token_level_losses


def split_sentences(text: str) -> List[str]:
    text = (text or "").strip()
    if not text: return []
    chunks = re.split(r"(?<=[。！？.!?；;：:])\s+", text)
    return [c.strip() for c in chunks if c.strip()] or [text]


def is_trivial_sentence(sentence: str) -> bool:
    s = sentence.replace(" ", "")
    if not s or all(c in string.punctuation for c in s) or s.isdigit(): return True
    if len(s) == 1 and s.isalpha(): return True
    return len(s.split()) <= 1


def pad_list(input_list: list, target_len: int) -> list:
    return input_list + [0.0] * max(0, target_len - len(input_list)) if len(input_list) < target_len else input_list[
        :target_len]


def calc_tail_difference(list1: list, list2: list) -> list:
    if not list2: return []
    if len(list1) < len(list2): return [0.0] * len(list2)
    return [abs(a - b) for a, b in zip(list1[-len(list2):], list2)]


class SingleSentencePredictor:
    def __init__(self, config: AppConfig):
        self.config = config
        self.device = get_device()
        self.ppl_calc = GPT2PerplexityCalculator(config)

        model_path = Path(config.head_model_folder) / config.head_model_name
        try:
            self.head_model = torch.load(str(model_path), map_location=self.device, weights_only=False)
        except TypeError:
            self.head_model = torch.load(str(model_path), map_location=self.device)
        self.head_model.eval()

    def _extract_features(self, sentences: List[str]) -> torch.Tensor:
        s1 = sentences[0] if len(sentences) > 0 else ""
        s2 = sentences[1] if len(sentences) > 1 else s1
        s3 = sentences[2] if len(sentences) > 2 else s2

        s1 = s1 + " " + s1 if is_trivial_sentence(s1) else s1
        s2 = s2 + " " + s2 if is_trivial_sentence(s2) else s2
        s3 = s3 + " " + s3 if is_trivial_sentence(s3) else s3

        _, _, loss3 = self.ppl_calc.calculate_perplexity(s3)
        _, _, loss123 = self.ppl_calc.calculate_perplexity(f"{s1} {s2} {s3}")

        return torch.tensor(pad_list(calc_tail_difference(loss123, loss3), self.config.feature_pad_len),
                            dtype=torch.float32)

    def predict_scores(self, sentences: List[str]) -> List[float]:
        if not sentences: return []
        votes = [[] for _ in range(len(sentences))]

        with torch.no_grad():
            for start in range(0, max(1, len(sentences) - self.config.window_size + 1), self.config.window_step):
                window = sentences[start: start + self.config.window_size]
                feat = self._extract_features(window)
                deberta_feat = self.head_model.extract_deberta_PPL(" ".join(window), feat, 1)
                score = torch.sigmoid(self.head_model(deberta_feat)).item()

                for i in range(start, min(start + self.config.window_size, len(sentences))):
                    votes[i].append(score)

        # 重构：引入置信度加权投票 (Confidence-weighted voting)
        final_scores = []
        for v in votes:
            if not v:
                final_scores.append(0.5)
                continue
            if len(v) <= 2:
                final_scores.append(sum(v) / len(v))
                continue

            # 距离0.5越远，置信度越高，权重越大
            weights = [abs(p - 0.5) * 2 for p in v]
            total_w = sum(weights)
            if total_w == 0:
                final_scores.append(sum(v) / len(v))
            else:
                norm_w = [w / total_w for w in weights]
                final_scores.append(sum(p * w for p, w in zip(v, norm_w)))

        return final_scores


def find_switch_index(results: List[dict], threshold: float) -> int:
    """寻找从人类写作切换到AI生成的索引点"""
    for idx, row in enumerate(results):
        if row["confidence"] >= threshold:
            return idx
    return len(results)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--single_text", type=str, default="title: Rodrigo Duterte...")
    parser.add_argument("--head_folder", type=str, default=r"F:\wy\work1\windows_log\windows_webuse")
    parser.add_argument("--head_model", type=str, default="epoch-last.pkl")
    parser.add_argument("--window_size", type=int, default=3)
    parser.add_argument("--window_step", type=int, default=1)
    args = parser.parse_args()

    config = AppConfig(
        head_model_folder=args.head_folder, head_model_name=args.head_model,
        window_size=args.window_size, window_step=args.window_step
    )

    text = (args.single_text or "").strip()
    if not text:
        print(json.dumps({"sentences": [], "switch_sentence_index": 0, "model_used": "empty"}))
        return

    predictor = SingleSentencePredictor(config)
    sents = split_sentences(text)
    scores = predictor.predict_scores(sents)

    rows = []
    for idx, (sent, score) in enumerate(zip(sents, scores)):
        label = "AIGT" if score >= config.ai_threshold else "HWT"
        rows.append(
            {"index": idx, "text": sent, "label": label, "confidence": round(score, 4), "ai_ratio": round(score, 4)})

    switch_idx = find_switch_index(rows, config.ai_threshold)
    print(json.dumps({"sentences": rows, "switch_sentence_index": switch_idx, "model_used": "v5-weighted-vote"},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()