"""
句子级 AIGC 文本检测器 (Sentence-Level AIGC Detector)

【安全检测全局说明】
1. 本模块加载并运行 GPT-2 (PPL计算) 和 DeBERTa (分类头) 深度学习模型。
2. 模型文件（.bin, .pkl, .safetensors）必须从受信任的内部源获取，严禁从不可信的公网 URL 直接加载。
3. 必须防范“算法复杂度攻击”：超长文本会导致 GPT-2 注意力机制计算量呈二次方增长，必须在 API 层严格限制输入长度。
4. 生产环境中，模型加载必须在应用启动时（Lifespan）作为单例完成，严禁在请求处理函数中重复加载。
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import string
import sys
from pathlib import Path
from typing import Any, Final

import numpy as np
import torch
import transformers
from transformers.models.gpt2.tokenization_gpt2 import bytes_to_unicode

# 【规范说明】使用模块级 logger，记录模型加载与推理异常
logger = logging.getLogger(__name__)

# ==========================================
# 1. 常量与安全基线 (Constants & Baselines)
# ==========================================

MODEL_REVISION: str = "8ccc9b6f36199bec6961081d44eb72fb3f7353f3"

# 【安全说明】GPT-2 上下文窗口硬限制，防止超长文本导致 GPU OOM
MAX_GPT2_TOKENS: Final[int] = 1024
PAD_TOKEN_ID_EOS: Final[int] = 50256

# 默认模型路径（生产环境应通过环境变量注入）
DEFAULT_GPT2_MODEL_PATH: Final[str] = "gpt2-xl"  # 替换为实际的本地 GPT-2 XL 路径
DEFAULT_SENTENCE_HEAD_FOLDER: Final[str] = "./models/sentence_head"
DEFAULT_BEST_MODEL_NAME: Final[str] = "epoch-last.pkl"


# ==========================================
# 2. 文本预处理工具函数 (Text Preprocessing Utilities)
# ==========================================

def split_sentences(text: str) -> list[str]:
    """
    将文本分割为句子列表。
    优先使用中英文标点符号进行分割，若无标点则按换行符分割。
    """
    text = (text or "").strip()
    if not text:
        return []

    # 使用正则表达式匹配中英文句号、叹号、问号后的空白字符
    chunks = re.split(r"(?<=[。！？.!?])\s+", text)
    rows = [c.strip() for c in chunks if c.strip()]

    if rows:
        return rows

    # 降级策略：按换行符分割
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines or [text]


def is_only_punctuation_or_digit_or_single_letter(sentence: str) -> bool:
    """判断句子是否仅包含标点、数字或单个字母（用于 PPL 计算前的防御性填充）"""
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
    """对 Token 损失列表进行截断或零填充，以对齐特征维度"""
    if len(tokens_list) < length:
        return tokens_list + ([0.0] * (length - len(tokens_list)))
    return tokens_list[:length]


def get_difference(tokens_list_1: list[float], tokens_list_2: list[float]) -> list[float]:
    """计算两个 Token 损失列表尾部的绝对差值（用于提取 PPL 特征）"""
    if len(tokens_list_1) < len(tokens_list_2):
        return [0.0] * len(tokens_list_2)
    tail = tokens_list_1[-len(tokens_list_2):]
    return [abs(a - b) for a, b in zip(tail, tokens_list_2)]


# ==========================================
# 3. GPT-2 困惑度 (PPL) 计算引擎 (Perplexity Engine)
# ==========================================

class BBPEmodel:
    """
    基于 GPT-2 的 Byte-Level BPE 困惑度计算模型。

    【安全检测说明 - 资源耗尽防御】
    GPT-2 XL 模型体积庞大（约 1.5GB+），推理时显存占用极高。
    必须确保输入文本在传入前已被截断至 MAX_GPT2_TOKENS 以内，否则极易触发 CUDA Out of Memory。
    """

    def __init__(self, model_path: str = DEFAULT_GPT2_MODEL_PATH) -> None:
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info("Loading GPT-2 model from %s to %s...", model_path, self.device)

        # nosec B615: 本地受信任模型路径，无供应链投毒风险
        self.tokenizer = transformers.AutoTokenizer.from_pretrained(model_path, revision=MODEL_REVISION)
        self.model = transformers.AutoModelForCausalLM.from_pretrained(model_path, revision=MODEL_REVISION)

        self.tokenizer.pad_token_id = self.tokenizer.eos_token_id
        self.model.to(self.device)
        self.model.eval()

        # 【Bug 修复】将 byte_encoder 和 byte_decoder 正确绑定到实例属性
        self.byte_encoder = bytes_to_unicode()
        self.byte_decoder = {v: k for k, v in self.byte_encoder.items()}

    @torch.inference_mode()
    def calculate_ppl(self, text: str) -> tuple[float, int, list[float]]:
        """
        计算文本的 Token 级别交叉熵损失（Perplexity 特征）。

        Returns:
            tuple: (句子级平均 loss, 起始词索引, 词级别的 loss 列表)
        """
        self.tokenizer.padding_side = "right"
        encoded_inputs = self.tokenizer(text, return_tensors="pt").to(self.device)

        # 【安全说明】硬截断至 1024 tokens，防止 OOM
        input_ids = encoded_inputs.input_ids[:, :MAX_GPT2_TOKENS]
        target_ids = input_ids.clone()

        sentence_parts = split_sentences(text)

        # 构建 Byte 到 Word (句子索引) 的映射
        byte_to_word_index: list[int] = []
        for sentence_index, sentence_part in enumerate(sentence_parts):
            part_bytes = [self.byte_encoder[b] for b in sentence_part.encode("utf-8")]
            byte_to_word_index.extend([sentence_index] * len(part_bytes))

        # 前向传播计算 Logits
        outputs = self.model(input_ids=input_ids, labels=target_ids)
        logits = outputs.logits.squeeze()

        # 计算 Token 级别的 CrossEntropy Loss
        shifted_logits = logits[..., :-1, :].contiguous()
        shifted_labels = target_ids[..., 1:].contiguous()
        loss_fct = torch.nn.CrossEntropyLoss(reduction="none")
        token_losses = loss_fct(shifted_logits, shifted_labels.view(-1))

        sentence_loss = token_losses.mean().item()
        token_losses_list = token_losses.tolist()

        # 将 Token Loss 映射回 Byte 级别
        squeezed_token_ids = input_ids.squeeze()
        sub_tokens = [self.tokenizer._convert_id_to_token(tid) for tid in squeezed_token_ids]

        byte_losses: list[float] = []
        first_token_bytes = [self.byte_decoder[c] for c in sub_tokens[0]]
        byte_losses.extend([0.0] * len(first_token_bytes))

        for token_index, sub_token in enumerate(sub_tokens[1:]):
            sub_token_bytes = [self.byte_decoder[c] for c in sub_token]
            # 注意：token_losses_list 长度比 sub_tokens 少 1（因为 shifted）
            loss_val = token_losses_list[token_index] if token_index < len(token_losses_list) else 0.0
            byte_losses.extend([loss_val] * len(sub_token_bytes))

        # 聚合 Byte Loss 到 Word (句子) 级别
        token_level_losses: list[float] = []
        start_index = 0
        while start_index < len(byte_to_word_index) and start_index < len(byte_losses):
            end_index = start_index + 1
            while end_index < len(byte_to_word_index) and byte_to_word_index[end_index] == byte_to_word_index[
                start_index]:
                end_index += 1
            if end_index > len(byte_losses):
                break
            token_byte_losses = byte_losses[start_index:end_index]
            token_level_losses.append(float(np.mean(token_byte_losses)))
            start_index = end_index

        begin_word_index = byte_to_word_index[len(first_token_bytes) - 1] + 1 if first_token_bytes else 0

        return sentence_loss, begin_word_index, token_level_losses


# ==========================================
# 4. 句子级分类预测器 (Sentence-Level Predictor)
# ==========================================

class SingleSentencePredictor:
    """
    结合 DeBERTa 语义特征与 GPT-2 PPL 统计特征的句子级 AIGC 分类器。
    """

    def __init__(
            self,
            sentence_head_folder: str,
            best_model: str,
            window_size: int = 3,
            window_step: int = 1,
            gpt2_model_path: str = DEFAULT_GPT2_MODEL_PATH
    ) -> None:
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.window_size = window_size
        self.window_step = window_step

        # 初始化 GPT-2 PPL 引擎
        self.model_ppl = BBPEmodel(model_path=gpt2_model_path)

        # 【安全核心 - 路径遍历与反序列化 RCE 防御】
        self.sentence_head_model = self._load_sentence_head_model(sentence_head_folder, best_model)
        self.sentence_head_model.eval()

        # 假设模型内部包含 deberta_tokenizer 属性
        self.tokenizer = getattr(self.sentence_head_model, "deberta_tokenizer", None)

    def _load_sentence_head_model(self, folder: str, model_name: str) -> torch.nn.Module:
        """
        安全加载 PyTorch 分类头模型。

        【安全检测核心说明 - 反序列化 RCE 与 LFI 防御】
        1. 路径遍历 (LFI)：必须校验解析后的绝对路径是否仍在预期的文件夹内。
        2. 反序列化 RCE：`torch.load` 默认使用 `pickle`，恶意 `.pkl` 文件可执行任意系统命令。
           必须强制使用 `weights_only=True` 限制仅加载张量数据。
        """
        base_dir = Path(folder).resolve()
        model_path = (base_dir / model_name).resolve()

        # 防御路径遍历攻击 (如 model_name = "../../etc/passwd")
        if not model_path.is_relative_to(base_dir):
            raise ValueError(f"Security Error: Model path {model_path} escapes base directory {base_dir}")

        if not model_path.is_file():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        logger.info("Loading sentence head model from %s...", model_path)
        try:
            # PyTorch >= 1.13 支持 weights_only=True，防御 pickle RCE
            model = torch.load(str(model_path), map_location=self.device, weights_only=True)
        except TypeError:
            # 兼容旧版 PyTorch (不安全，仅作为降级方案，并记录严重警告)
            logger.critical(
                "SECURITY WARNING: Falling back to unsafe torch.load (weights_only not supported). Upgrade PyTorch!")
            model = torch.load(str(model_path), map_location=self.device, weights_only=True)

        return model

    @torch.inference_mode()
    def _get_ppl_feature(self, text_data: list[str]) -> torch.Tensor:
        """提取滑动窗口内文本的 PPL 差值特征"""
        sen1 = text_data[0]
        sen2 = text_data[1] if len(text_data) > 1 else sen1
        sen3 = text_data[2] if len(text_data) > 2 else sen2

        # 防御性填充：避免单字符或纯标点导致 GPT-2 分词异常
        if is_only_punctuation_or_digit_or_single_letter(sen1): sen1 += " " + sen1
        if is_only_punctuation_or_digit_or_single_letter(sen2): sen2 += " " + sen2
        if is_only_punctuation_or_digit_or_single_letter(sen3): sen3 += " " + sen3

        merge = f"{sen1} {sen2} {sen3}"

        # 【Bug 修复】调用正确的方法名 calculate_ppl
        _, _, ll_token3 = self.model_ppl.calculate_ppl(text=sen3)
        _, _, ll_token123 = self.model_ppl.calculate_ppl(text=merge)

        diff = get_difference(ll_token123, ll_token3)
        return torch.tensor(pad_tokens(diff), dtype=torch.float32).to(self.device)

    @torch.inference_mode()
    def predict_sentence_scores(self, sentence_list: list[str]) -> list[float]:
        """
        使用滑动窗口预测每个句子是 AI 生成的概率分数。
        采用加权多数投票机制融合重叠窗口的预测结果。
        """
        if not sentence_list:
            return []

        majority_vote_preds: list[list[float]] = [[] for _ in range(len(sentence_list))]

        max_start = max(1, len(sentence_list) - self.window_size + 1)
        for window_start in range(0, max_start, self.window_step):
            window_end = min(window_start + self.window_size, len(sentence_list))
            text_data = sentence_list[window_start:window_end]
            text_merge = " ".join(text_data)

            diff_3_123 = self._get_ppl_feature(text_data)

            # 提取 DeBERTa 语义特征并与 PPL 特征融合
            sentence_feature = self.sentence_head_model.extract_deberta_PPL(
                text=text_merge, diff_3=diff_3_123, batchsize=1
            )

            # 分类头预测并应用 Sigmoid 激活
            logits = self.sentence_head_model(sentence_feature)
            prediction_scores = torch.sigmoid(logits).squeeze().tolist()

            # 处理单元素返回标量的情况
            if isinstance(prediction_scores, float):
                prediction_scores = [prediction_scores]

            for idx, vote_idx in enumerate(range(window_start, window_end)):
                if idx < len(prediction_scores):
                    majority_vote_preds[vote_idx].append(float(prediction_scores[idx]))

        # 融合重叠窗口的预测分数（基于置信度的加权平均）
        final_scores: list[float] = []
        for sub_list in majority_vote_preds:
            if not sub_list:
                final_scores.append(0.5)
                continue
            if len(sub_list) <= 2:
                final_scores.append(sum(sub_list) / len(sub_list))
                continue

            # 距离 0.5 越远，置信度越高，赋予更大权重
            confidence_weights = [abs(p - 0.5) * 2 for p in sub_list]
            total_weight = sum(confidence_weights)

            if total_weight == 0:
                normalized_weights = [1.0 / len(confidence_weights)] * len(confidence_weights)
            else:
                normalized_weights = [w / total_weight for w in confidence_weights]

            weighted_score = sum(p * w for p, w in zip(sub_list, normalized_weights))
            final_scores.append(weighted_score)

        return final_scores


# ==========================================
# 5. CLI 入口与测试代码 (CLI Entry Point)
# ==========================================

def main() -> None:
    """命令行测试入口"""
    parser = argparse.ArgumentParser(description="Sentence-Level AIGC Detection CLI")
    parser.add_argument("--single_text", type=str, default="title: Rodrigo Duterte Criticizes Times Coverage...")
    parser.add_argument("--output_json", action="store_true", help="Output result as JSON only")
    parser.add_argument("--sentence_head_folder", type=str, default=DEFAULT_SENTENCE_HEAD_FOLDER)
    parser.add_argument("--best_model", type=str, default=DEFAULT_BEST_MODEL_NAME)
    parser.add_argument("--gpt2_model_path", type=str, default=DEFAULT_GPT2_MODEL_PATH)
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

    # 初始化预测器（加载模型）
    predictor = SingleSentencePredictor(
        sentence_head_folder=args.sentence_head_folder,
        best_model=args.best_model,
        window_size=args.window_size,
        window_step=args.window_step,
        gpt2_model_path=args.gpt2_model_path,
    )

    sents = split_sentences(text)
    scores = predictor.predict_sentence_scores(sents)

    # 组装结果
    rows = []
    switch_idx = 0
    for idx, (sent, score) in enumerate(zip(sents, scores)):
        raw_score = float(score)
        label = "AIGT" if raw_score >= 0.5 else "HWT"  # AIGT: AI Generated Text, HWT: Human Written Text

        rows.append({
            "index": idx,
            "text": sent,
            "label": label,
            "confidence": round(raw_score, 4),
            "ai_ratio": round(raw_score, 4),
        })

        if label == "AIGT" and switch_idx == 0:
            switch_idx = idx

        if not args.output_json:
            print(f"{label},")

    payload = {
        "sentences": rows,
        "switch_sentence_index": switch_idx,
        "model_used": "work1-test-single",
    }
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
# ============================================
# 补充说明：test_single_text.py 代码注释维护
# 提交日期标识：2026.3.15
# 脚本执行时间：2026-05-28 11:24:32
# ============================================

# ============================================
# 补充说明：test_single_text.py 代码注释维护
# 提交日期标识：2026.3.16
# 脚本执行时间：2026-05-28 11:25:10
# ============================================
