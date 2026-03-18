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
        self.model.to(self.device)

        self.byte_encoder = bytes_to_unicode()
        self.byte_decoder = {v: k for k, v in self.byte_encoder.items()}

    def calculate_perplexity(self, text):
        self.tokenizer.padding_side = 'right'
        encoded_inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=1024).to(self.device)
        token_ids = encoded_inputs.input_ids
        target_ids = encoded_inputs.input_ids.clone()

        sentence_parts = split_sentences(text)
        byte_to_word_index = []
        for s_idx, s_part in enumerate(sentence_parts):
            part_bytes = [self.byte_encoder[b] for b in s_part.encode("utf-8")]
            byte_to_word_index.extend([s_idx] * len(part_bytes))

        outputs = self.model(input_ids=token_ids, labels=target_ids)
        logits = outputs.logits.squeeze()
        loss_fn = torch.nn.CrossEntropyLoss(reduction="none")
        token_losses = loss_fn(logits[..., :-1, :].contiguous().view(-1, logits.size(-1)),
                               target_ids[..., 1:].contiguous().view(-1))

        sentence_loss = token_losses.mean().item()
        token_losses_list = token_losses.tolist()

        sub_tokens = [self.tokenizer._convert_id_to_token(tid) for tid in token_ids.squeeze()]
        byte_losses = [0] * len([self.byte_decoder[c] for c in sub_tokens[0]])
        for t_idx, sub_token in enumerate(sub_tokens[1:]):
            byte_losses.extend([token_losses_list[t_idx]] * len([self.byte_decoder[c] for c in sub_token]))

        token_level_losses = []
        start = 0
        while start < len(byte_to_word_index) and start < len(byte_losses):
            end = start + 1
            while end < len(byte_to_word_index) and byte_to_word_index[end] == byte_to_word_index[start]:
                end += 1
            if end > len(byte_losses): break
            token_level_losses.append(np.mean(byte_losses[start:end]))
            start = end

        first_token_bytes = [self.byte_decoder[c] for c in sub_tokens[0]]
        begin_word_idx = byte_to_word_index[len(first_token_bytes) - 1] + 1 if first_token_bytes else 0
        return sentence_loss, begin_word_idx, token_level_losses


def split_sentences(text: str) -> list[str]:
    text = (text or "").strip()
    if not text: return []
    chunks = re.split(r"(?<=[。！？.!?])\s+", text)
    rows = [c.strip() for c in chunks if c.strip()]
    return rows if rows else [line.strip() for line in text.splitlines() if line.strip()] or [text]


def is_trivial_sentence(sentence: str) -> bool:
    sentence = sentence.replace(" ", "")
    if not sentence: return True
    if all(char in string.punctuation for char in sentence): return True
    if sentence.isdigit() or (len(sentence) == 1 and sentence.isalpha()): return True
    return len(sentence.split()) == 1


def pad_list(input_list: list, target_len: int = 512, pad_val=0.0) -> list:
    if len(input_list) < target_len:
        return input_list + [pad_val] * (target_len - len(input_list))
    return input_list[:target_len]


def calc_tail_difference(list1: list, list2: list) -> list:
    if len(list1) < len(list2): return [0.0] * len(list2)
    return [abs(a - b) for a, b in zip(list1[-len(list2):], list2)]


class SingleSentencePredictor:
    def __init__(self, head_folder: str, model_name: str, win_size: int, win_step: int):
        self.device = get_device()
        self.window_size = win_size
        self.window_step = win_step
        self.ppl_calculator = GPT2PerplexityCalculator()

        model_path = Path(head_folder) / model_name
        try:
            self.head_model = torch.load(str(model_path), map_location=self.device, weights_only=False)
        except TypeError:
            self.head_model = torch.load(str(model_path), map_location=self.device)
        self.head_model.eval()

    def _extract_ppl_features(self, sentences: list[str]) -> torch.Tensor:
        sen1 = sentences[0] if len(sentences) > 0 else ""
        sen2 = sentences[1] if len(sentences) > 1 else sen1
        sen3 = sentences[2] if len(sentences) > 2 else sen2

        sen1 = sen1 + " " + sen1 if is_trivial_sentence(sen1) else sen1
        sen2 = sen2 + " " + sen2 if is_trivial_sentence(sen2) else sen2
        sen3 = sen3 + " " + sen3 if is_trivial_sentence(sen3) else sen3

        _, _, loss_3 = self.ppl_calculator.calculate_perplexity(sen3)
        _, _, loss_123 = self.ppl_calculator.calculate_perplexity(f"{sen1} {sen2} {sen3}")

        diff = calc_tail_difference(loss_123, loss_3)
        return torch.tensor(pad_list(diff))

    def predict_scores(self, sentences: list[str]) -> list[float]:
        if not sentences: return []

        votes = [[] for _ in range(len(sentences))]
        with torch.no_grad():
            for start in range(0, max(1, len(sentences) - self.window_size + 1), self.window_step):
                window_sents = sentences[start: start + self.window_size]
                features = self._extract_ppl_features(window_sents)
                deberta_feat = self.head_model.extract_deberta_PPL(" ".join(window_sents), features, 1)
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

    rows, switch_idx = [], 0
    for idx, (sent, score) in enumerate(zip(sents, scores)):
        label = "AIGT" if score >= 0.5 else "HWT"
        rows.append(
            {"index": idx, "text": sent, "label": label, "confidence": round(score, 4), "ai_ratio": round(score, 4)})
        if label == "AIGT" and switch_idx == 0: switch_idx = idx

    print(json.dumps({"sentences": rows, "switch_sentence_index": switch_idx, "model_used": "v2-clean"},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()