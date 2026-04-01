import argparse
import json
import re
import string
import sys
from pathlib import Path
import torch
import transformers
import numpy as np
from transformers.models.gpt2.tokenization_gpt2 import bytes_to_unicode


def get_device():
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


class GPT2PerplexityCalculator:
    def __init__(self, model_path='D:\wy\gpt2-xl'):
        self.device = get_device()
        self.tokenizer = transformers.AutoTokenizer.from_pretrained(model_path)
        self.model = transformers.AutoModelForCausalLM.from_pretrained(model_path)
        self.tokenizer.pad_token_id = self.tokenizer.eos_token_id
        self.model.eval()
        self.model.to(self.device)

        self.byte_encoder = bytes_to_unicode()
        self.byte_decoder = {v: k for k, v in self.byte_encoder.items()}

    def calculate_perplexity(self, text):
        if not text.strip():
            return 0.0, 0, []

        self.tokenizer.padding_side = 'right'
        encoded = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=1024).to(self.device)
        input_ids = encoded.input_ids

        sentence_parts = split_sentences(text)
        byte_to_word_idx = []
        for s_idx, part in enumerate(sentence_parts):
            byte_to_word_idx.extend([s_idx] * len(part.encode("utf-8")))

        with torch.no_grad():
            outputs = self.model(input_ids=input_ids, labels=input_ids)

        # 增强维度处理鲁棒性
        logits = outputs.logits
        if logits.dim() == 3:
            logits = logits.squeeze(0)

        shift_logits = logits[:-1, :].contiguous()
        shift_labels = input_ids.squeeze()[1:].contiguous()

        loss_fn = torch.nn.CrossEntropyLoss(reduction="none")
        token_losses = loss_fn(shift_logits, shift_labels)
        sentence_loss = token_losses.mean().item()
        token_losses_list = token_losses.cpu().tolist()

        sub_tokens = [self.tokenizer._convert_id_to_token(tid) for tid in input_ids.squeeze()]
        if not sub_tokens:
            return sentence_loss, 0, []

        byte_losses = [0.0] * len(sub_tokens[0])
        for t_idx, st in enumerate(sub_tokens[1:]):
            byte_losses.extend([token_losses_list[t_idx]] * len(st))

        token_level_losses = []
        start = 0
        while start < len(byte_to_word_idx) and start < len(byte_losses):
            end = start + 1
            while end < len(byte_to_word_idx) and byte_to_word_idx[end] == byte_to_word_idx[start]:
                end += 1
            if end > len(byte_losses): break
            token_level_losses.append(float(np.mean(byte_losses[start:end])))
            start = end

        begin_word_idx = byte_to_word_idx[len(sub_tokens[0]) - 1] + 1 if sub_tokens[0] else 0
        return sentence_loss, begin_word_idx, token_level_losses


def split_sentences(text: str) -> list[str]:
    text = (text or "").strip()
    if not text: return []
    # 优化正则：支持更多中英文标点符号
    chunks = re.split(r"(?<=[。！？.!?；;：:])\s+", text)
    rows = [c.strip() for c in chunks if c.strip()]
    return rows if rows else [text]


def is_trivial_sentence(sentence: str) -> bool:
    s = sentence.replace(" ", "")
    if not s: return True
    if all(c in string.punctuation for c in s): return True
    if s.isdigit() or (len(s) == 1 and s.isalpha()): return True
    return len(s.split()) <= 1


def pad_list(input_list: list, target_len: int = 512, pad_val=0.0) -> list:
    diff = target_len - len(input_list)
    if diff > 0:
        return input_list + [pad_val] * diff
    return input_list[:target_len]


def calc_tail_difference(list1: list, list2: list) -> list:
    if not list2: return []
    if len(list1) < len(list2): return [0.0] * len(list2)
    return [abs(a - b) for a, b in zip(list1[-len(list2):], list2)]


class SingleSentencePredictor:
    def __init__(self, head_folder: str, model_name: str, win_size: int, win_step: int):
        self.device = get_device()
        self.window_size = win_size
        self.window_step = win_step
        self.ppl_calc = GPT2PerplexityCalculator()

        model_path = Path(head_folder) / model_name
        try:
            self.head_model = torch.load(str(model_path), map_location=self.device, weights_only=False)
        except TypeError:
            self.head_model = torch.load(str(model_path), map_location=self.device)
        self.head_model.eval()

    def _extract_features(self, sentences: list[str]) -> torch.Tensor:
        s1 = sentences[0] if len(sentences) > 0 else ""
        s2 = sentences[1] if len(sentences) > 1 else s1
        s3 = sentences[2] if len(sentences) > 2 else s2

        s1 = s1 + " " + s1 if is_trivial_sentence(s1) else s1
        s2 = s2 + " " + s2 if is_trivial_sentence(s2) else s2
        s3 = s3 + " " + s3 if is_trivial_sentence(s3) else s3

        _, _, loss3 = self.ppl_calc.calculate_perplexity(s3)
        _, _, loss123 = self.ppl_calc.calculate_perplexity(f"{s1} {s2} {s3}")

        return torch.tensor(pad_list(calc_tail_difference(loss123, loss3)), dtype=torch.float32)

    def predict_scores(self, sentences: list[str]) -> list[float]:
        if not sentences: return []
        votes = [[] for _ in range(len(sentences))]

        with torch.no_grad():
            for start in range(0, max(1, len(sentences) - self.window_size + 1), self.window_step):
                window = sentences[start: start + self.window_size]
                feat = self._extract_features(window)
                deberta_feat = self.head_model.extract_deberta_PPL(" ".join(window), feat, 1)
                score = torch.sigmoid(self.head_model(deberta_feat)).item()

                for i in range(start, min(start + self.window_size, len(sentences))):
                    votes[i].append(score)

        return [sum(v) / len(v) if v else 0.5 for v in votes]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--single_text", type=str, default="title: Rodrigo Duterte...")
    parser.add_argument("--output_json", action="store_true")
    parser.add_argument("--sentence_head_folder", type=str, default="F:\\wy\\work1\\windows_log\\windows_webuse")
    parser.add_argument("--best_model", type=str, default="epoch-last.pkl")
    parser.add_argument("--window_size", type=int, default=3)
    parser.add_argument("--window_step", type=int, default=1)
    args = parser.parse_args()

    text = (args.single_text or "").strip()
    if not text:
        print(json.dumps({"sentences": [], "switch_sentence_index": 0, "model_used": "empty"}))
        return

    predictor = SingleSentencePredictor(args.sentence_head_folder, args.best_model, args.window_size, args.window_step)
    sents = split_sentences(text)
    scores = predictor.predict_scores(sents)

    rows, switch_idx = [], -1
    for idx, (sent, score) in enumerate(zip(sents, scores)):
        label = "AIGT" if score >= 0.5 else "HWT"
        rows.append(
            {"index": idx, "text": sent, "label": label, "confidence": round(score, 4), "ai_ratio": round(score, 4)})
        if label == "AIGT" and switch_idx == -1: switch_idx = idx
    if switch_idx == -1: switch_idx = len(sents)

    print(json.dumps({"sentences": rows, "switch_sentence_index": switch_idx, "model_used": "v3-robust"},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()