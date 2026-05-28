"""
词级 AIGC 文本检测器 (Word-Level AIGC Detector)

【安全检测全局说明】
1. 本模块使用 DeBERTa + CRF 架构进行词级别的 AI 生成文本边界检测。
2. 必须严格限制输入文本的单词数量，防止滑动窗口机制导致计算量激增，引发 CPU/GPU 资源耗尽 (DoS)。
3. 模型加载必须锁定特定的 Commit Hash (revision)，防御 HuggingFace 供应链投毒攻击。
4. 本地权重文件加载必须校验路径，防御路径遍历 (Path Traversal) 攻击。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
from pathlib import Path
from typing import Any, Final

import numpy as np
import torch
import torch.nn as nn
from torchcrf import CRF
from transformers import AutoModel, AutoTokenizer, BatchEncoding

# 【规范说明】使用模块级 logger，记录模型加载与推理异常
logger = logging.getLogger(__name__)

# ==========================================
# 1. 常量与安全基线 (Constants & Baselines)
# ==========================================

# 【安全核心 - 供应链安全】锁定 DeBERTa 模型的精确 Commit Hash，防止上游仓库被劫持或篡改
DEBERTA_REVISION: Final[str] = "8ccc9b6f36199bec6961081d44eb72fb3f7353f3"

# 【安全说明】业务限制常量，防止恶意用户提交超长文本导致滑动窗口计算量耗尽算力 (DoS)
MAX_INPUT_WORDS: Final[int] = 2000

# 滑动窗口默认参数
BASE_WINDOW_SIZE: Final[int] = 512
BASE_STRIDE: Final[int] = 384
SHORT_WINDOW_CAP: Final[int] = 256

# 默认模型路径
DEFAULT_MODEL_NAME: Final[str] = "microsoft/deberta-v3-base"
DEFAULT_WEIGHTS_FILENAME: Final[str] = "deberta_CRF(new)_best.pt"


# ==========================================
# 2. 工具函数 (Utility Functions)
# ==========================================

def set_seed(seed: int) -> None:
    """设置全局随机种子，确保模型推理与初始化的可重复性"""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def build_adaptive_windows(
        doc_len: int,
        base_window: int = BASE_WINDOW_SIZE,
        base_stride: int = BASE_STRIDE,
        short_window_cap: int = SHORT_WINDOW_CAP
) -> list[tuple[int, int]]:
    """
    根据文档长度构建自适应滑动窗口。
    对于短文本动态调整窗口大小，对于长文本使用固定窗口和步长。
    """
    if doc_len <= 0:
        return [(0, 0)]

    if doc_len > base_window:
        win_size = base_window
        stride = base_stride
    else:
        win_size = min(short_window_cap, doc_len)
        if win_size >= doc_len and doc_len > 2:
            win_size = max(2, int(np.ceil(doc_len * 0.75)))
        stride = max(1, win_size // 2)

    if win_size >= doc_len:
        return [(0, doc_len)]

    starts = list(range(0, doc_len - win_size + 1, stride))
    last_start = doc_len - win_size
    if starts[-1] != last_start:
        starts.append(last_start)

    # 确保至少有两个窗口以覆盖中间区域
    if len(starts) < 2 and doc_len > win_size:
        mid_start = (doc_len - win_size) // 2
        starts.append(mid_start)
        starts = sorted(set(starts))

    return [(s, s + win_size) for s in starts]


def decode_boundary_from_scores(score_sum: np.ndarray) -> int:
    """
    基于累积得分计算最佳的 AI/人类文本切换边界 (Switch Boundary)。
    使用动态规划思想寻找使目标函数最大化的分割点。
    """
    n = len(score_sum)
    if n <= 0:
        return 0

    prefix_neg = np.cumsum(-score_sum)
    prefix_pos = np.cumsum(score_sum)
    total_pos = prefix_pos[-1]

    # 目标函数：左侧负样本得分 + 右侧正样本得分
    objective = prefix_neg + (total_pos - prefix_pos)
    best_boundary = int(np.argmax(objective))

    return max(0, min(best_boundary, n - 1))


# ==========================================
# 3. 核心模型定义 (Core Model Definition)
# ==========================================

class DeBERTaCRFTagger(nn.Module):
    """
    基于 DeBERTa 和条件随机场 (CRF) 的序列标注模型。
    用于预测每个单词是 AI 生成 (1) 还是人类编写 (0)。
    """

    def __init__(self, model_name: str, num_labels: int = 2, dropout_rate: float = 0.1) -> None:
        super().__init__()
        self.num_labels = num_labels

        # 【安全说明】强制使用 revision 锁定模型版本，防御供应链攻击
        self.deberta = AutoModel.from_pretrained(model_name, revision=DEBERTA_REVISION)
        self.dropout = nn.Dropout(dropout_rate)

        hidden_size = self.deberta.config.hidden_size
        self.classifier = nn.Linear(hidden_size, num_labels)

        # 权重初始化
        nn.init.xavier_uniform_(self.classifier.weight)
        nn.init.constant_(self.classifier.bias, 0)

        self.crf = CRF(num_labels, batch_first=True)

    def forward(
            self,
            input_ids: torch.Tensor,
            attention_mask: torch.Tensor,
            labels: torch.Tensor | None = None
    ) -> torch.Tensor | list[list[int]]:
        """
        前向传播。
        若提供 labels，则返回 CRF 负对数似然损失 (用于训练)；
        否则返回解码后的标签序列 (用于推理)。
        """
        outputs = self.deberta(input_ids, attention_mask=attention_mask)
        sequence_output = self.dropout(outputs.last_hidden_state)
        logits = self.classifier(sequence_output)

        mask = attention_mask.bool()

        if labels is not None:
            # 训练模式：计算 CRF Loss
            crf_labels = labels.clone()
            crf_labels[crf_labels == -100] = 0  # 忽略 padding 和 special tokens
            loss = -self.crf(logits, crf_labels, mask=mask, reduction="mean")
            return loss

        # 推理模式：Viterbi 解码
        predictions = self.crf.decode(logits, mask=mask)

        # 将变长列表填充回原始序列长度，以便后续处理
        padded_predictions = []
        seq_len = attention_mask.size(1)
        for pred in predictions:
            pad_len = seq_len - len(pred)
            padded_predictions.append(pred + [0] * pad_len)

        return torch.tensor(padded_predictions, device=input_ids.device)


# ==========================================
# 4. 推理与解码逻辑 (Inference & Decoding Logic)
# ==========================================

def decode_window_word_predictions(encoding: BatchEncoding, pred_ids: list[int]) -> list[int]:
    """
    将 Token 级别的预测结果对齐并聚合到 Word (单词) 级别。
    采用多数投票机制 (Majority Voting) 处理 Sub-word 分词问题。
    """
    attention_mask = encoding["attention_mask"][0].tolist()
    pred_ids = pred_ids[: len(attention_mask)]

    # 尝试获取 word_ids (Fast Tokenizer 特性)
    try:
        word_ids = encoding.word_ids(batch_index=0)
    except Exception:
        word_ids = None

    # 降级方案：使用 special_tokens_mask
    if word_ids is None:
        special_tokens_mask = encoding["special_tokens_mask"][0].tolist()
        word_level_preds = []
        for i, is_special in enumerate(special_tokens_mask):
            if attention_mask[i] == 1 and not is_special:
                word_level_preds.append(int(pred_ids[i]))
        return word_level_preds

    # 标准方案：基于 word_ids 进行多数投票
    per_word_votes: dict[int, list[int]] = {}
    for i, wid in enumerate(word_ids):
        if wid is None or attention_mask[i] == 0:
            continue
        per_word_votes.setdefault(wid, [0, 0])
        label = int(pred_ids[i])
        per_word_votes[wid][label] += 1

    word_level_preds = []
    for wid in sorted(per_word_votes.keys()):
        votes = per_word_votes[wid]
        # 若 AI 标签(1) 票数严格大于 人类标签(0) 票数，则判定为 AI
        word_level_preds.append(1 if votes[1] > votes[0] else 0)

    return word_level_preds


@torch.inference_mode()
def infer_document_with_sliding_windows(
        model: DeBERTaCRFTagger,
        words: list[str],
        tokenizer: AutoTokenizer,
        max_len: int,
        device: torch.device
) -> tuple[list[int], int, np.ndarray]:
    """
    使用滑动窗口机制对长文档进行词级推理。

    【安全检测说明 - 资源耗尽防御】
    长文本会被切分为多个窗口分别送入 GPU 推理。若文本极长，窗口数量将线性增加，
    导致推理时间大幅增加。必须在调用前校验 `len(words)` 是否超过安全阈值。
    """
    doc_len = len(words)
    windows = build_adaptive_windows(doc_len)

    vote_counts = np.zeros((doc_len, 2), dtype=np.int32)
    score_sum = np.zeros(doc_len, dtype=np.float32)

    for start, end in windows:
        window_words = words[start:end]

        # 分词与编码
        encoding = tokenizer(
            window_words,
            is_split_into_words=True,
            max_length=max_len,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
            return_special_tokens_mask=True,
        )

        input_ids = encoding["input_ids"].to(device)
        attention_mask = encoding["attention_mask"].to(device)

        # 模型推理
        predictions = model(input_ids, attention_mask)
        pred_ids = predictions[0].detach().cpu().tolist()

        # 解码并对齐到全局单词索引
        word_preds = decode_window_word_predictions(encoding, pred_ids)
        for local_idx, pred in enumerate(word_preds):
            global_idx = start + local_idx
            if global_idx < doc_len:
                pred_i = int(pred)
                vote_counts[global_idx, pred_i] += 1
                # 累积得分：AI(1) 加 1，人类(0) 减 1
                score_sum[global_idx] += 1.0 if pred_i == 1 else -1.0

    # 计算全局切换边界
    boundary = decode_boundary_from_scores(score_sum)

    # 基于边界生成最终的词级标签 (边界及之前为人类，之后为 AI)
    pred_word_labels = [0 if i <= boundary else 1 for i in range(doc_len)]

    return pred_word_labels, boundary, vote_counts


# ==========================================
# 5. CLI 入口 (CLI Entry Point)
# ==========================================

def main() -> None:
    """命令行测试入口"""
    parser = argparse.ArgumentParser(description="Word-Level AIGC Detection CLI")
    parser.add_argument("--single_text", type=str, default="")
    parser.add_argument("--output_json", action="store_true")
    parser.add_argument("--model_name", type=str, default=DEFAULT_MODEL_NAME)
    parser.add_argument("--best_model_path", type=str,
                        default=os.path.join(os.path.dirname(__file__), DEFAULT_WEIGHTS_FILENAME))
    parser.add_argument("--max_len", type=int, default=512)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    text = (args.single_text or "").strip()
    if not text:
        print(
            json.dumps({"boundary_idx": 0, "word_labels": [], "model_used": "work2-single-empty"}, ensure_ascii=False))
        return

    # 【安全说明】防御超长文本导致的滑动窗口计算量 DoS
    words = text.split()
    if len(words) > MAX_INPUT_WORDS:
        logger.error("Input text exceeds maximum word limit (%d > %d)", len(words), MAX_INPUT_WORDS)
        print(json.dumps({"error": "Text too long", "model_used": "work2-error"}, ensure_ascii=False))
        return

    if not words:
        print(
            json.dumps({"boundary_idx": 0, "word_labels": [], "model_used": "work2-single-empty"}, ensure_ascii=False))
        return

    set_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # 【安全说明】强制使用 revision 锁定模型版本
    tokenizer = AutoTokenizer.from_pretrained(args.model_name, revision=DEBERTA_REVISION)
    model = DeBERTaCRFTagger(args.model_name, 2).to(device)

    # 【安全核心 - 路径遍历与反序列化 RCE 防御】
    base_dir = Path(__file__).parent.resolve()
    model_path = Path(args.best_model_path).resolve()

    # 防御路径遍历攻击 (如 best_model_path = "../../etc/passwd")
    if not model_path.is_relative_to(base_dir):
        logger.critical("Security Error: Model path %s escapes base directory %s", model_path, base_dir)
        raise ValueError("Invalid model path")

    if not model_path.is_file():
        raise FileNotFoundError(f"Model weights not found: {model_path}")

    logger.info("Loading model weights from %s...", model_path)
    # 【安全说明】weights_only=True 防御 Pickle 反序列化 RCE
    ckpt = torch.load(str(model_path), map_location=device, weights_only=True)
    state = ckpt.get("model_state_dict", ckpt)
    model.load_state_dict(state)
    model.eval()

    # 执行推理
    pred_word_labels, boundary, _ = infer_document_with_sliding_windows(
        model, words, tokenizer, args.max_len, device
    )

    payload = {
        "boundary_idx": int(boundary),
        "word_labels": [int(x) for x in pred_word_labels],
        "model_used": "work2-deberta-crf-single",
    }
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
# ============================================
# 补充说明：deberta_CRF(new)_single_text.py 代码注释维护
# 提交日期标识：2026.3.15
# 脚本执行时间：2026-05-28 11:24:39
# ============================================

# ============================================
# 补充说明：deberta_CRF(new)_single_text.py 代码注释维护
# 提交日期标识：2026.3.16
# 脚本执行时间：2026-05-28 11:25:16
# ============================================

# ============================================
# 补充说明：deberta_CRF(new)_single_text.py 代码注释维护
# 提交日期标识：2026.3.19
# 脚本执行时间：2026-05-28 11:25:58
# ============================================

# ============================================
# 补充说明：deberta_CRF(new)_single_text.py 代码注释维护
# 提交日期标识：2026.3.22
# 脚本执行时间：2026-05-28 11:26:40
# ============================================

# ============================================
# 补充说明：deberta_CRF(new)_single_text.py 代码注释维护
# 提交日期标识：2026.3.24
# 脚本执行时间：2026-05-28 11:27:21
# ============================================
