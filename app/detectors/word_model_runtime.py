"""词级别 AIGC 检测模型与滑动窗口推理模块。

本模块实现了基于 DeBERTa + CRF 的序列标注模型，并提供了一套完整的
长文档滑动窗口推理机制。通过自适应窗口切分、子词级别预测聚合（投票法）
以及基于累积得分的边界解码，实现对长文本中“人类撰写-AI生成”切换点的精准定位。
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from torchcrf import CRF
from transformers import AutoModel, PreTrainedTokenizerBase

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量定义
# ---------------------------------------------------------------------------

# 模型与权重配置
MODEL_REVISION: str = "8ccc9b6f36199bec6961081d44eb72fb3f7353f3"
DEFAULT_DROPOUT_RATE: float = 0.1

# 标签与损失计算配置
LABEL_HUMAN: int = 0
LABEL_AI: int = 1
NUM_LABELS: int = 2
IGNORE_LABEL_INDEX: int = -100  # HuggingFace 标准忽略索引（通常用于 Padding Token）

# 滑动窗口与自适应策略参数
DEFAULT_MAX_LEN: int = 512
DEFAULT_BASE_WINDOW: int = 512
DEFAULT_BASE_STRIDE: int = 256
DEFAULT_SHORT_WINDOW_CAP: int = 256
SHORT_WINDOW_RATIO: float = 0.75
MIN_WINDOW_SIZE: int = 2


# ---------------------------------------------------------------------------
# 模型定义
# ---------------------------------------------------------------------------

class DeBERTaCRFTagger(nn.Module):
    """基于 DeBERTa 和条件随机场 (CRF) 的词级别序列标注模型。

    该模型使用 DeBERTa 提取上下文语义特征，并通过线性分类器映射到标签空间，
    最后利用 CRF 层学习标签之间的转移概率，从而输出全局最优的标签序列。

    Attributes:
        num_labels: 标签类别数量（通常为 2：人类撰写 / AI 生成）。
        deberta: 预训练的 DeBERTa 基础模型。
        dropout: 用于防止过拟合的 Dropout 层。
        classifier: 将隐藏状态映射到标签空间的线性层。
        crf: 条件随机场层，用于序列解码和损失计算。
    """

    def __init__(
        self,
        model_name: str,
        num_labels: int = NUM_LABELS,
        dropout_rate: float = DEFAULT_DROPOUT_RATE,
    ) -> None:
        """初始化 DeBERTa-CRF 模型。

        Args:
            model_name: HuggingFace 模型名称或本地路径。
            num_labels: 分类标签的数量。
            dropout_rate: Dropout 层的丢弃概率。
        """
        super().__init__()
        self.num_labels = num_labels

        # 加载预训练 DeBERTa 模型（指定 revision 确保版本一致性）
        self.deberta = AutoModel.from_pretrained(model_name, revision=MODEL_REVISION)
        self.dropout = nn.Dropout(dropout_rate)

        # 构建分类头并使用 Xavier 均匀分布初始化权重
        hidden_size = self.deberta.config.hidden_size
        self.classifier = nn.Linear(hidden_size, num_labels)
        nn.init.xavier_uniform_(self.classifier.weight)
        nn.init.constant_(self.classifier.bias, 0)

        # 初始化 CRF 层
        self.crf = CRF(num_labels, batch_first=True)

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        labels: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """模型的前向传播。

        在训练模式下计算 CRF 负对数似然损失；在推理模式下解码最优标签序列。

        Args:
            input_ids: 输入 Token ID 张量，形状为 `(batch_size, seq_len)`。
            attention_mask: 注意力掩码张量，形状为 `(batch_size, seq_len)`。
            labels: 真实标签张量（仅训练时提供），形状为 `(batch_size, seq_len)`。
                    Padding 位置的标签应为 `IGNORE_LABEL_INDEX` (-100)。

        Returns:
            如果 `labels` 不为空，返回标量损失值 (Loss)；
            否则返回填充后的预测标签张量，形状为 `(batch_size, seq_len)`。
        """
        outputs = self.deberta(input_ids, attention_mask=attention_mask)
        sequence_output = self.dropout(outputs.last_hidden_state)
        logits = self.classifier(sequence_output)

        mask = attention_mask.bool()

        # --- 训练模式：计算 CRF 损失 ---
        if labels is not None:
            crf_labels = labels.clone()
            # CRF 层不支持负数索引，需将 -100 (Ignore Index) 替换为 0。
            # 由于 mask 的作用，这些位置的预测不会影响梯度计算。
            crf_labels[crf_labels == IGNORE_LABEL_INDEX] = 0
            # torchcrf 返回的是对数似然，需取负号作为损失函数
            loss = -self.crf(logits, crf_labels, mask=mask, reduction="mean")
            return loss

        # --- 推理模式：解码最优路径 ---
        predictions = self.crf.decode(logits, mask=mask)

        # torchcrf.decode 返回的是变长列表（去除了 padding），需重新填充以对齐 batch 维度
        seq_len = attention_mask.size(1)
        padded_predictions = []
        for pred in predictions:
            pad_len = seq_len - len(pred)
            padded_predictions.append(pred + [LABEL_HUMAN] * pad_len)

        return torch.tensor(padded_predictions, device=input_ids.device)


# ---------------------------------------------------------------------------
# 解码与窗口构建工具函数
# ---------------------------------------------------------------------------

def decode_window_word_predictions(
    encoding: Any,
    pred_ids: list[int],
) -> list[int]:
    """将 Token 级别的预测聚合为 Word（词）级别的预测。

    由于分词器（Tokenizer）会将一个词拆分为多个子词（Sub-word），
    本函数通过多数投票机制（Majority Voting）或过滤特殊 Token 的方式，
    将子词级别的预测结果还原到原始词级别。

    Args:
        encoding: HuggingFace Tokenizer 的编码输出对象（BatchEncoding）。
        pred_ids: 当前窗口内 Token 级别的预测标签列表。

    Returns:
        词级别的预测标签列表，长度等于当前窗口内的有效词数。
    """
    attention_mask = encoding["attention_mask"][0].tolist()
    # 截断预测结果以匹配实际 attention_mask 长度
    pred_ids = pred_ids[: len(attention_mask)]

    # 尝试获取 word_ids（快速分词器 Fast Tokenizer 支持此方法）
    try:
        word_ids = encoding.word_ids(batch_index=0)
    except (AttributeError, TypeError, ValueError):
        # 慢速分词器（Slow Tokenizer）不支持 word_ids，回退到特殊 Token 掩码
        word_ids = None

    # 回退策略：使用 special_tokens_mask 过滤
    if word_ids is None:
        special_tokens_mask = encoding["special_tokens_mask"][0].tolist()
        word_level_preds = []
        for i, is_special in enumerate(special_tokens_mask):
            # 仅保留非 Padding 且非特殊 Token（如 [CLS], [SEP]）的预测
            if attention_mask[i] == 1 and not is_special:
                word_level_preds.append(int(pred_ids[i]))
        return word_level_preds

    # 主策略：基于 word_ids 进行子词投票
    per_word_votes: dict[int, list[int]] = {}
    for i, word_id in enumerate(word_ids):
        # 跳过特殊 Token (word_id 为 None) 和 Padding Token
        if word_id is None or attention_mask[i] == 0:
            continue

        if word_id not in per_word_votes:
            per_word_votes[word_id] = [0, 0]

        label = int(pred_ids[i])
        per_word_votes[word_id][label] += 1

    # 按词索引排序，并根据多数投票决定最终标签
    word_level_preds = []
    for word_id in sorted(per_word_votes.keys()):
        votes = per_word_votes[word_id]
        # 如果 AI 标签 (1) 的票数严格大于人类标签 (0)，则判定为 AI
        final_label = LABEL_AI if votes[LABEL_AI] > votes[LABEL_HUMAN] else LABEL_HUMAN
        word_level_preds.append(final_label)

    return word_level_preds


def build_adaptive_windows(
    doc_len: int,
    base_window: int = DEFAULT_BASE_WINDOW,
    base_stride: int = DEFAULT_BASE_STRIDE,
    short_window_cap: int = DEFAULT_SHORT_WINDOW_CAP,
) -> list[tuple[int, int]]:
    """根据文档长度构建自适应的滑动窗口。

    对于长文档，使用固定的基础窗口和步长；对于短文档，动态缩小窗口尺寸
    以增加重叠率，从而在有限长度内提取更丰富的上下文特征。

    Args:
        doc_len: 文档的总词数。
        base_window: 长文档的基础窗口大小。
        base_stride: 长文档的滑动步长。
        short_window_cap: 短文档的窗口大小上限。

    Returns:
        窗口列表，每个元素为 `(start_index, end_index)` 的元组。
    """
    if doc_len <= 0:
        return [(0, 0)]

    # 策略 1：长文档使用固定窗口和步长
    if doc_len > base_window:
        win_size = base_window
        stride = base_stride
    # 策略 2：短文档动态调整窗口大小
    else:
        win_size = min(short_window_cap, doc_len)
        # 如果文档极短，按比例缩小窗口以强制产生重叠
        if win_size >= doc_len and doc_len > 2:
            win_size = max(MIN_WINDOW_SIZE, int(np.ceil(doc_len * SHORT_WINDOW_RATIO)))
        stride = max(1, win_size // 2)

    # 如果窗口已经能覆盖整个文档，直接返回单窗口
    if win_size >= doc_len:
        return [(0, doc_len)]

    # 生成滑动窗口起点
    starts = list(range(0, doc_len - win_size + 1, stride))
    last_start = doc_len - win_size

    # 确保最后一个窗口严格对齐到文档末尾
    if starts[-1] != last_start:
        starts.append(last_start)

    # 兜底逻辑：如果文档略长于窗口但步长导致只有一个窗口，强制在中间插入一个窗口
    if len(starts) < 2 and doc_len > win_size:
        mid_start = (doc_len - win_size) // 2
        starts.append(mid_start)
        starts = sorted(set(starts))

    return [(start, start + win_size) for start in starts]


def decode_boundary_from_scores(score_sum: np.ndarray) -> int:
    """基于累积得分计算人类撰写与 AI 生成的最佳切换边界。

    算法思想：
    假设序列前缀为人类撰写（得分为负），后缀为 AI 生成（得分为正）。
    遍历所有可能的切分点 `i`，计算目标函数：
    `Objective(i) = sum(score[0:i] == 0) + sum(score[i:n] == 1)`
    通过前缀和优化，将时间复杂度降至 O(N)。

    Args:
        score_sum: 每个词位置的累积得分数组（AI 投票为 +1，人类投票为 -1）。

    Returns:
        最佳边界索引（表示该索引及之前为人类撰写，之后为 AI 生成）。
    """
    n = len(score_sum)
    if n <= 0:
        return 0

    # prefix_neg[i]: 前 i 个词中，人类标签的累计得分（即 -score_sum 的累加）
    prefix_neg = np.cumsum(-score_sum)
    # prefix_pos[i]: 前 i 个词中，AI 标签的累计得分
    prefix_pos = np.cumsum(score_sum)

    total_pos = prefix_pos[-1]

    # objective[i] = (前 i 个词的人类得分) + (后 n-i 个词的 AI 得分)
    # 后 n-i 个词的 AI 得分 = total_pos - prefix_pos[i]
    objective = prefix_neg + (total_pos - prefix_pos)

    best_boundary = int(np.argmax(objective))
    return max(0, min(best_boundary, n - 1))


# ---------------------------------------------------------------------------
# 核心推理函数
# ---------------------------------------------------------------------------

def infer_document_with_sliding_windows(
    model: DeBERTaCRFTagger,
    words: list[str],
    tokenizer: PreTrainedTokenizerBase,
    max_len: int = DEFAULT_MAX_LEN,
    device: torch.device | str = "cpu",
    base_window: int = DEFAULT_BASE_WINDOW,
    base_stride: int = DEFAULT_BASE_STRIDE,
    short_window_cap: int = DEFAULT_SHORT_WINDOW_CAP,
) -> tuple[list[int], int, np.ndarray]:
    """使用滑动窗口机制对长文档进行词级别 AIGC 推理。

    该函数将长文档切分为多个重叠窗口，分别进行模型推理，
    然后通过投票机制聚合预测结果，并最终解码出全局切换边界。

    Args:
        model: 已加载权重的 DeBERTaCRFTagger 模型实例。
        words: 待检测文档的词列表（已分词）。
        tokenizer: 对应的 HuggingFace 分词器。
        max_len: 模型输入的最大 Token 长度。
        device: 推理使用的计算设备（如 'cuda' 或 'cpu'）。
        base_window: 滑动窗口基础大小。
        base_stride: 滑动窗口步长。
        short_window_cap: 短文档窗口上限。

    Returns:
        一个包含三个元素的元组：
        - `pred_word_labels`: 基于边界划分的最终词级标签列表 (0=人类, 1=AI)。
        - `boundary`: 计算得出的全局切换边界索引。
        - `vote_counts`: 形状为 `(doc_len, 2)` 的数组，记录每个词获得的人类/AI投票数。
    """
    doc_len = len(words)
    windows = build_adaptive_windows(
        doc_len,
        base_window=base_window,
        base_stride=base_stride,
        short_window_cap=short_window_cap,
    )

    # 初始化投票计数器和累积得分数组
    vote_counts = np.zeros((doc_len, NUM_LABELS), dtype=np.int32)
    score_sum = np.zeros(doc_len, dtype=np.float32)

    with torch.no_grad():
        for start, end in windows:
            window_words = words[start:end]

            # 对当前窗口进行编码
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

            # 将 Token 级预测解码为 Word 级预测
            word_preds = decode_window_word_predictions(encoding, pred_ids)

            # 将局部窗口的预测结果映射回全局文档索引并累加得分
            for local_idx, pred in enumerate(word_preds):
                global_idx = start + local_idx
                if global_idx < doc_len:
                    pred_label = int(pred)
                    vote_counts[global_idx, pred_label] += 1
                    # AI 标签记为 +1，人类标签记为 -1，用于后续边界计算
                    score_sum[global_idx] += 1.0 if pred_label == LABEL_AI else -1.0

    # 解码全局切换边界
    boundary = decode_boundary_from_scores(score_sum)

    # 根据边界生成最终的硬标签序列（边界及之前为人类，之后为 AI）
    pred_word_labels = [LABEL_HUMAN if i <= boundary else LABEL_AI for i in range(doc_len)]

    return pred_word_labels, boundary, vote_counts
# ============================================
# 补充说明：word_model_runtime.py 代码注释维护
# 提交日期标识：2026.3.15
# 脚本执行时间：2026-05-28 11:24:26
# ============================================
