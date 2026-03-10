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


class BBPEmodel:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.gpt2_tokenizer = transformers.AutoTokenizer.from_pretrained('D:\wy\gpt2-xl')
        self.gpt2_model = transformers.AutoModelForCausalLM.from_pretrained('D:\wy\gpt2-xl')
        self.gpt2_tokenizer.pad_token_id = self.gpt2_tokenizer.eos_token_id
        self.gpt2_model.to(self.device)

        # 修复Bug: 将局部变量改为实例属性，并补充 byte_decoder
        self.byte_encoder = bytes_to_unicode()
        self.byte_decoder = {v: k for k, v in self.byte_encoder.items()}

    def forward_calc_ppl(self, text):  # 修复Bug: 方法名与调用处统一
        self.gpt2_tokenizer.padding_side = 'right'
        encoded_inputs = self.gpt2_tokenizer(text, return_tensors="pt").to(
            self.device)  # 修复Bug: self.tokenizer -> self.gpt2_tokenizer
        token_ids = encoded_inputs.input_ids[:, :1024]
        target_ids = encoded_inputs.input_ids[:, :1024]
        sentence_parts = split_sentences(text)

        byte_to_word_index = []
        for sentence_index, sentence_part in enumerate(sentence_parts):
            part_bytes = [self.byte_encoder[b] for b in sentence_part.encode("utf-8")]
            byte_to_word_index.extend([sentence_index] * len(part_bytes))

        model_outputs = self.gpt2_model(input_ids=token_ids,
                                        labels=target_ids)  # 修复Bug: self.language_model -> self.gpt2_model
        logits = model_outputs.logits.squeeze()
        shifted_logits = logits[..., :-1, :].contiguous()
        shifted_labels = target_ids[..., 1:].contiguous()
        loss_function = torch.nn.CrossEntropyLoss(reduction="none")
        token_losses = loss_function(shifted_logits, shifted_labels.view(-1))
        sentence_loss = token_losses.mean().item()
        token_losses = token_losses.tolist()

        squeezed_token_ids = token_ids.squeeze()
        sub_tokens = [self.gpt2_tokenizer._convert_id_to_token(token_id) for token_id in squeezed_token_ids]

        byte_losses = []
        first_token_bytes = [self.byte_decoder[c] for c in sub_tokens[0]]
        byte_losses.extend([0] * len(first_token_bytes))
        for token_index, sub_token in enumerate(sub_tokens[1:]):
            sub_token_bytes = [self.byte_decoder[c] for c in sub_token]
            byte_losses.extend([token_losses[token_index]] * len(sub_token_bytes))

        token_level_losses = []
        start_index = 0
        while start_index < len(byte_to_word_index) and start_index < len(byte_losses):
            end_index = start_index + 1
            while end_index < len(byte_to_word_index) and byte_to_word_index[end_index] == byte_to_word_index[
                start_index]:
                end_index += 1
            if end_index > len(byte_losses):
                break
            token_byte_losses = byte_losses[start_index:end_index]
            token_level_losses.append(np.mean(token_byte_losses))
            start_index = end_index

        begin_word_index = byte_to_word_index[len(first_token_bytes) - 1] + 1 if len(first_token_bytes) > 0 else 0
        return [sentence_loss, begin_word_index, token_level_losses]


def split_sentences(text: str) -> list[str]:
    text = (text or "").strip()
    if not text: return []
    chunks = re.split(r"(?<=[。！？.!?])\s+", text)
    rows = [c.strip() for c in chunks if c.strip()]
    return rows if rows else [line.strip() for line in text.splitlines() if line.strip()] or [text]


def is_only_punctuation_or_digit_or_single_letter(sentence: str) -> bool:
    sentence = sentence.replace(" ", "")
    if not sentence: return True
    if all(char in string.punctuation for char in sentence): return True
    if sentence.isdigit(): return True
    if len(sentence) == 1 and sentence.isalpha(): return True
    if len(sentence.split()) == 1: return True
    return False


def pad_tokens(tokens_list: list[float], length: int = 512) -> list[float]:
    if len(tokens_list) < length:
        tokens_list = tokens_list + ([0] * (length - len(tokens_list)))
    elif len(tokens_list) > length:
        tokens_list = tokens_list[:length]
    return tokens_list


def get_difference(tokens_list_1: list[float], tokens_list_2: list[float]) -> list[float]:
    if len(tokens_list_1) < len(tokens_list_2):
        return [0.0 for _ in tokens_list_2]
    tail = tokens_list_1[-len(tokens_list_2):]
    return [abs(a - b) for a, b in zip(tail, tokens_list_2)]


class SingleSentencePredictor:
    def __init__(self, sentence_head_folder: str, best_model: str, window_size: int, window_step: int) -> None:
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.window_size = window_size
        self.window_step = window_step
        self.model_ppl = BBPEmodel()
        model_path = Path(sentence_head_folder) / best_model
        try:
            self.sentence_head_model = torch.load(str(model_path), map_location=self.device, weights_only=False)
        except TypeError:
            self.sentence_head_model = torch.load(str(model_path), map_location=self.device)
        self.sentence_head_model.eval()

    def _get_ppl_feature(self, text_data: list[str]) -> torch.Tensor:
        sen1 = text_data[0] if len(text_data) > 0 else ""
        sen2 = text_data[1] if len(text_data) > 1 else sen1
        sen3 = text_data[2] if len(text_data) > 2 else sen2

        for sen in [sen1, sen2, sen3]:
            if is_only_punctuation_or_digit_or_single_letter(sen):
                sen = sen + " " + sen

        merge = sen1 + " " + sen2 + " " + sen3
        _, _, ll_token3 = self.model_ppl.forward_calc_ppl(text=sen3)
        _, _, ll_token123 = self.model_ppl.forward_calc_ppl(text=merge)
        diff = get_difference(ll_token123, ll_token3)
        return torch.tensor(pad_tokens(diff))

    def predict_sentence_scores(self, sentence_list: list[str]) -> list[float]:
        with torch.no_grad():
            if not sentence_list: return []
            majority_vote_preds = [[] for _ in range(len(sentence_list))]
            for window_start in range(0, max(1, len(sentence_list) - self.window_size + 1), self.window_step):
                text_data = sentence_list[window_start: window_start + self.window_size]
                text_merge = " ".join(text_data)
                diff_3_123 = self._get_ppl_feature(text_data)
                sentence_feature = self.sentence_head_model.extract_deberta_PPL(text=text_merge, diff_3=diff_3_123,
                                                                                batchsize=1)

                # 修复Bug: prediction_score 是标量，不能用 idx 索引
                prediction_score = torch.sigmoid(self.sentence_head_model(sentence_feature)).item()

                for vote_idx in range(window_start, min(window_start + self.window_size, len(sentence_list))):
                    majority_vote_preds[vote_idx].append(float(prediction_score))

        rows = []
        for sub_list in majority_vote_preds:
            if not sub_list: rows.append(0.5); continue
            rows.append(sum(sub_list) / len(sub_list))
        return rows


def main() -> None:
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
        print(json.dumps({"sentences": [], "switch_sentence_index": 0, "model_used": "empty"}, ensure_ascii=False))
        return

    predictor = SingleSentencePredictor(args.sentence_head_folder, args.best_model, args.window_size, args.window_step)
    sents = split_sentences(text)
    scores = predictor.predict_sentence_scores(sents)

    rows = []
    switch_idx = 0
    for idx, (sent, score) in enumerate(zip(sents, scores)):
        label = "AIGT" if score >= 0.5 else "HWT"
        rows.append(
            {"index": idx, "text": sent, "label": label, "confidence": round(score, 4), "ai_ratio": round(score, 4)})
        if label == "AIGT" and switch_idx == 0: switch_idx = idx

    print(json.dumps({"sentences": rows, "switch_sentence_index": switch_idx, "model_used": "work1-test-single"},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()