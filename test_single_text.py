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
        self.do_generate = None
        self.text = None
        self.generate_len = 1024
        self.gpt2_tokenizer = transformers.AutoTokenizer.from_pretrained('你的gpt2-xl地址')# nosec B615 本地模型，无供应链风险
        self.gpt2_model = transformers.AutoModelForCausalLM.from_pretrained('你的gpt2-xl地址')# nosec B615 本地模型，无供应链风险
        self.gpt2_tokenizer.pad_token_id = self.gpt2_tokenizer.eos_token_id
        self.gpt2_model.to(self.device)
        byte_encoder = bytes_to_unicode()

    def ppl(self, text):
        self.gpt2_tokenizer.padding_side = 'right'
        
        encoded_inputs = self.tokenizer(text, return_tensors="pt").to(self.device)
        token_ids = encoded_inputs.input_ids[:, :1024]
        target_ids = encoded_inputs.input_ids[:, :1024]
        sentence_parts = split_sentences(text)

        byte_to_word_index = []
        for sentence_index, sentence_part in enumerate(sentence_parts):
            part_bytes = [self.byte_encoder[b] for b in sentence_part.encode("utf-8")]
            byte_to_word_index.extend([sentence_index] * len(part_bytes))

        model_outputs = self.language_model(input_ids=token_ids, labels=target_ids)
        logits = model_outputs.logits.squeeze()
        shifted_logits = logits[..., :-1, :].contiguous()
        shifted_labels = target_ids[..., 1:].contiguous()
        loss_function = torch.nn.CrossEntropyLoss(reduction="none")
        token_losses = loss_function(shifted_logits, shifted_labels.view(-1))
        sentence_loss = token_losses.mean().item()
        token_losses = token_losses.tolist()

        squeezed_token_ids = token_ids.squeeze()
        sub_tokens = [self.tokenizer._convert_id_to_token(token_id) for token_id in squeezed_token_ids]

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
            while end_index < len(byte_to_word_index) and byte_to_word_index[end_index] == byte_to_word_index[start_index]:
                end_index += 1
            if end_index > len(byte_losses):
                break
            token_byte_losses = byte_losses[start_index:end_index]
            token_level_losses.append(np.mean(token_byte_losses))
            start_index = end_index

        begin_word_index = byte_to_word_index[len(first_token_bytes) - 1] + 1 if len(first_token_bytes) > 0 else 0

        return [sentence_loss, begin_word_index, token_level_losses]

    def forward(self, data):
        self.text = data.get("text")
        return self.ppl(text=self.text)
    
    
    
def split_sentences(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks = re.split(r"(?<=[。！？.!?])\s+", text)
    rows = [c.strip() for c in chunks if c.strip()]
    if rows:
        return rows
    return [line.strip() for line in text.splitlines() if line.strip()] or [text]


def is_only_punctuation_or_digit_or_single_letter(sentence: str) -> bool:
    sentence = sentence.replace(" ", "")
    if not sentence:
        return True
    if all(char in string.punctuation for char in sentence):
        return True
    if sentence.isdigit():
        return True
    if len(sentence) == 1 and sentence.isalpha():
        return True
    if len(sentence.split()) == 1:
        return True
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
            self.sentence_head_model = torch.load(
                str(model_path),
                map_location=self.device,
                weights_only=True,
            )
        except TypeError:
            self.sentence_head_model = torch.load(str(model_path), map_location=self.device, weights_only=True)
        
        
        self.sentence_head_model.eval()
        self.tokenizer = self.sentence_head_model.deberta_tokenizer

    def _get_ppl_feature(self, text_data: list[str]) -> torch.Tensor:
        sen1 = text_data[0]
        if len(text_data) == 1:
            sen2 = text_data[0]
            sen3 = text_data[0]
        elif len(text_data) == 2:
            sen2 = text_data[1]
            sen3 = text_data[1]
        else:
            sen2 = text_data[1]
            sen3 = text_data[2]

        if is_only_punctuation_or_digit_or_single_letter(sen1):
            sen1 = sen1 + " " + sen1
        if is_only_punctuation_or_digit_or_single_letter(sen2):
            sen2 = sen2 + " " + sen2
        if is_only_punctuation_or_digit_or_single_letter(sen3):
            sen3 = sen3 + " " + sen3

        merge = sen1 + " " + sen2 + " " + sen3
        _, _, ll_token3 = self.model_ppl.forward_calc_ppl(text=sen3)
        _, _, ll_token123 = self.model_ppl.forward_calc_ppl(text=merge)
        diff = get_difference(ll_token123, ll_token3)
        return torch.tensor(pad_tokens(diff))

    def predict_sentence_scores(self, sentence_list: list[str]) -> list[float]:
        with torch.no_grad():
            if not sentence_list:
                return []

            majority_vote_preds = [[] for _ in range(len(sentence_list))]
            for window_start in range(0, max(1, len(sentence_list) - self.window_size + 1), self.window_step):
                text_data = sentence_list[window_start: window_start + self.window_size]
                text_merge = " ".join(text_data)
                diff_3_123 = self._get_ppl_feature(text_data)
                sentence_feature = self.sentence_head_model.extract_deberta_PPL(
                    text=text_merge,
                    diff_3=diff_3_123,
                    batchsize=1,
                )
                prediction_score = torch.sigmoid(self.sentence_head_model(sentence_feature)).tolist()[0]

                idx = 0
                for vote_idx in range(window_start, min(window_start + self.window_size, len(sentence_list))):
                    majority_vote_preds[vote_idx].append(float(prediction_score[idx]))
                    idx += 1

        rows = []
        for sub_list in majority_vote_preds:
            if not sub_list:
                rows.append(0.5)
                continue
            if len(sub_list) <= 2:
                rows.append(sum(sub_list) / len(sub_list))
                continue
            confidence_weights = [abs(p - 0.5) * 2 for p in sub_list]
            total_weight = sum(confidence_weights)
            if total_weight == 0:
                normalized_weights = [1.0 / len(confidence_weights)] * len(confidence_weights)
            else:
                normalized_weights = [w / total_weight for w in confidence_weights]
            rows.append(sum(p * w for p, w in zip(sub_list, normalized_weights)))
        return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--single_text", type=str, default="title: Rodrigo Duterte Criticizes Times Coverage of Philippine Drug Campaign. article: His article reported that since the beginning of July, about 2,000 people had been killed by the police and that there had been more than 3,500 unsolved killings in the country. Mr. Andanar said that the police have yet to identify any suspects in the other unsolved cases in which they've received information through their preliminary investigations. Mr. Andanar said that about a third of the unsolved killings had been identified as drug-related. Mr. Duterte's latest remarks on the killings have stirred some international criticism of his campaign. Mr. Duterte said in an interview that he could kill three million drug users and peddlers if he was sworn in as president on June 30, which would surpass the death toll of Mr. Asesina. Copyright \u00a9 2018 The Washington Times, LLC. Click here for reprint permission.")
    parser.add_argument("--output_json", action="store_true", help="print json only")
    parser.add_argument("--sentence_head_folder", type=str, default="F:\\wy\\work1\\windows_log\\windows_webuse")
    parser.add_argument("--best_model", type=str, default="epoch-last.pkl")
    parser.add_argument("--window_size", type=int, default=3)
    parser.add_argument("--window_step", type=int, default=1)
    args = parser.parse_args()

    text = (args.single_text or "").strip()
    if not text:
        payload = {
            "sentences": [],
            "switch_sentence_index": 0,
            "model_used": "work1-test-single-empty",
        }
        print(json.dumps(payload, ensure_ascii=False))
        return

    predictor = SingleSentencePredictor(
        sentence_head_folder=args.sentence_head_folder,
        best_model=args.best_model,
        window_size=args.window_size,
        window_step=args.window_step,
    )

    sents = split_sentences(text)
    scores = predictor.predict_sentence_scores(sents)

    labels = ["AIGT" if float(score) >= 0.5 else "HWT" for score in scores]

    rows = []
    for idx, (sent, score) in enumerate(zip(sents, scores)):
        raw_score = float(score)
        label = labels[idx]

        rows.append(
            {
                "index": idx,
                "text": sent,
                "label": label,
                "confidence": round(raw_score, 4),
                "ai_ratio": round(raw_score, 4),
            }
        )
        if not args.output_json:
            print(label + ",")

    switch_idx = 0
    for row in rows:
        if row["label"] == "AIGT":
            switch_idx = int(row["index"])
            break

    payload = {
        "sentences": rows,
        "switch_sentence_index": switch_idx,
        "model_used": "work1-test-single",
    }
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
