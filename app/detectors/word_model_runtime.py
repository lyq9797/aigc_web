# word_model_runtime.py — Version 5
# 改动：类型安全、语义化模型接口、向量化聚合、__all__ 导出、模块 docstring

"""Word-level model runtime for AI-generated text detection.

本模块实现了基于 DeBERTa + CRF 的词级别序列标注模型，以及配套的
滑动窗口推理引擎。主要功能包括：

- DeBERTaCRFTagger: 基于 DeBERTa 编码器和 CRF 解码器的序列标注模型。
- 滑动窗口推理: 自适应窗口分割、子词到词的聚合投票、全局边界解码。
- 工具函数: 窗口构建、边界解码、投票聚合等。

Typical usage::

    model = DeBERTaCRFTagger("microsoft/deberta-v3-base", num_labels=2)
    config = InferenceConfig(max_len=512, device=torch.device("cuda"))
    labels, boundary, votes = infer_document_with_sliding_windows(
        model, words, tokenizer, config=config,
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from torchcrf import CRF
from transformers import AutoModel

__all__ = [
    "DeBERTaCRFTagger",
    "InferenceConfig",
    "infer_document_with_sliding_windows",
    "build_adaptive_windows",
    "decode_boundary_from_scores",
    "decode_window_word_predictions",
]

logger = logging.getLogger(__name__)

# ======================== 常量 ========================

LABEL_NEGATIVE: int = 0
LABEL_POSITIVE: int = 1
NUM_BINARY_LABELS: int = 2

IGNORE_INDEX: int = -100
PAD_LABEL: int = 0
DEFAULT_DROPOUT: float = 0.1


# ======================== 配置 ========================


@dataclass
class InferenceConfig:
    """滑动窗口推理的配置参数。

    Attributes:
        max_len: tokenizer 最大序列长度，必须为正整数。
        base_window: 长文档使用的基础窗口大小（以词数为单位）。
        base_stride: 长文档的滑动步长（以词数为单位）。
        short_window_cap: 短文档窗口大小的上限。
        device: 推理使用的 torch 设备。
    """

    max_len: int = 512
    base_window: int = 512
    base_stride: int = 256
    short_window_cap: int = 256
    device: torch.device = field(default_factory=lambda: torch.device("cpu"))

    def __post_init__(self) -> None:
        """参数校验。"""
        if self.max_len <= 0:
            raise ValueError(f"max_len must be positive, got {self.max_len}")
        if self.base_window <= 0:
            raise ValueError(f"base_window must be positive, got {self.base_window}")
        if self.base_stride <= 0:
            raise ValueError(f"base_stride must be positive, got {self.base_stride}")
        if self.short_window_cap <= 0:
            raise ValueError(f"short_window_cap must be positive, got {self.short_window_cap}")
        if isinstance(self.device, str):
            self.device = torch.device(self.device)


# ======================== 模型定义 ========================


class DeBERTaCRFTagger(nn.Module):
    """基于 DeBERTa + CRF 的序列标注模型。

    该模型使用预训练 DeBERTa 作为编码器，接一个线性分类层和条件随机场 (CRF)
    层，用于词级别的二分类任务（如 AI 生成文本检测）。

    Attributes:
        num_labels: 标签类别数。
        deberta: DeBERTa 预训练编码器。
        dropout: Dropout 正则化层。
        classifier: 线性分类头。
        crf: 条件随机场解码层。
    """

    def __init__(
        self,
        model_name: str,
        num_labels: int,
        dropout_rate: float = DEFAULT_DROPOUT,
    ) -> None:
        """初始化模型。

        Args:
            model_name: HuggingFace 模型名称或本地路径。
            num_labels: 标签类别数量，必须为正整数。
            dropout_rate: Dropout 比率，取值范围 [0, 1)。

        Raises:
            ValueError: 当 num_labels 或 dropout_rate 不合法时。
        """
        super().__init__()

        if num_labels <= 0:
            raise ValueError(f"num_labels must be positive, got {num_labels}")
        if not 0.0 <= dropout_rate < 1.0:
            raise ValueError(f"dropout_rate must be in [0, 1), got {dropout_rate}")

        self.num_labels: int = num_labels
        self.deberta: AutoModel = AutoModel.from_pretrained(model_name)
        self.dropout: nn.Dropout = nn.Dropout(dropout_rate)

        hidden_size: int = self.deberta.config.hidden_size
        self.classifier: nn.Linear = nn.Linear(hidden_size, num_labels)
        nn.init.xavier_uniform_(self.classifier.weight)
        nn.init.constant_(self.classifier.bias, 0)

        self.crf: CRF = CRF(num_labels, batch_first=True)

        logger.info(
            "DeBERTaCRFTagger initialized: model=%s, labels=%d, dropout=%.2f",
            model_name,
            num_labels,
            dropout_rate,
        )

    def _encode(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        """DeBERTa 编码 + Dropout + 线性映射，返回 logits。

        Args:
            input_ids: 输入 token ID，形状 ``(batch, seq_len)``。
            attention_mask: 注意力掩码，形状 ``(batch, seq_len)``。

        Returns:
            形状为 ``(batch, seq_len, num_labels)`` 的 logits 张量。
        """
        outputs = self.deberta(input_ids, attention_mask=attention_mask)
        sequence_output = self.dropout(outputs.last_hidden_state)
        return self.classifier(sequence_output)

    def compute_loss(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        labels: torch.Tensor,
    ) -> torch.Tensor:
        """计算 CRF 负对数似然损失（训练模式）。

        Args:
            input_ids: 输入 token ID，形状 ``(batch, seq_len)``。
            attention_mask: 注意力掩码，形状 ``(batch, seq_len)``。
            labels: 标签张量，形状 ``(batch, seq_len)``。
                值为 ``IGNORE_INDEX`` 的位置会被替换为 ``PAD_LABEL``。

        Returns:
            标量损失张量。
        """
        logits = self._encode(input_ids, attention_mask)
        mask = attention_mask.bool()
        crf_labels = labels.clone()
        crf_labels[crf_labels == IGNORE_INDEX] = PAD_LABEL
        return -self.crf(logits, crf_labels, mask=mask, reduction="mean")

    def predict(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
    ) -> torch.Tensor:
        """CRF 解码预测（推理模式）。

        Args:
            input_ids: 输入 token ID，形状 ``(batch, seq_len)``。
            attention_mask: 注意力掩码，形状 ``(batch, seq_len)``。

        Returns:
            形状为 ``(batch, seq_len)`` 的预测标签张量，
            填充位置以 ``PAD_LABEL`` 补齐。
        """
        logits = self._encode(input_ids, attention_mask)
        mask = attention_mask.bool()
        predictions = self.crf.decode(logits, mask=mask)

        seq_len = attention_mask.size(1)
        padded_predictions: list[list[int]] = []
        for pred in predictions:
            pad_len = seq_len - len(pred)
            padded_predictions.append(pred + [PAD_LABEL] * pad_len)

        return torch.tensor(padded_predictions, device=input_ids.device)

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        labels: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """统一的前向传播入口，兼容训练和推理。

        Args:
            input_ids: 输入 token ID，形状 ``(batch, seq_len)``。
            attention_mask: 注意力掩码，形状 ``(batch, seq_len)``。
            labels: 可选标签张量。提供时返回损失，不提供时返回预测。

        Returns:
            训练模式返回标量 loss；推理模式返回预测张量。
        """
        if labels is not None:
            return self.compute_loss(input_ids, attention_mask, labels)
        return self.predict(input_ids, attention_mask)


# ======================== 子词聚合 ========================


def decode_window_word_predictions(
    encoding: Any,
    pred_ids: list[int],
) -> list[int]:
    """将子词级别的预测聚合为词级别的预测。

    聚合策略：
    1. **优先方案** — 使用 tokenizer 提供的 ``word_ids()`` 方法，
       对同一个词对应的所有子词预测进行多数投票。
    2. **回退方案** — 若 ``word_ids()`` 不可用，则通过
       ``special_tokens_mask`` 过滤特殊 token 后直接输出。

    Args:
        encoding: HuggingFace tokenizer 的编码输出 (BatchEncoding)。
        pred_ids: 子词级别的预测标签列表。

    Returns:
        词级别的预测标签列表，每个元素为 ``LABEL_NEGATIVE`` 或 ``LABEL_POSITIVE``。
    """
    if not pred_ids:
        logger.warning("decode_window_word_predictions received empty pred_ids")
        return []

    attention_mask: list[int] = encoding["attention_mask"][0].tolist()
    pred_ids = pred_ids[: len(attention_mask)]

    # 尝试获取 word_ids
    word_ids: list[int | None] | None = None
    try:
        word_ids = encoding.word_ids(batch_index=0)
    except (AttributeError, TypeError, IndexError) as exc:
        logger.debug("word_ids() unavailable, falling back to special_tokens_mask: %s", exc)

    # ---- 回退方案 ----
    if word_ids is None:
        special_tokens_mask: list[int] = encoding["special_tokens_mask"][0].tolist()
        return [
            int(pred_ids[i])
            for i, is_special in enumerate(special_tokens_mask)
            if attention_mask[i] == 1 and not is_special
        ]

    # ---- 主方案：多数投票 ----
    per_word_votes: dict[int, list[int]] = {}
    for i, wid in enumerate(word_ids):
        if wid is None or attention_mask[i] == 0:
            continue
        per_word_votes.setdefault(wid, [0, 0])
        label = int(pred_ids[i])
        if 0 <= label < NUM_BINARY_LABELS:
            per_word_votes[wid][label] += 1
        else:
            logger.warning("Unexpected label %d at token index %d, skipping", label, i)

    return [
        LABEL_POSITIVE if votes[LABEL_POSITIVE] > votes[LABEL_NEGATIVE] else LABEL_NEGATIVE
        for _, votes in sorted(per_word_votes.items())
    ]


# ======================== 窗口构建 ========================


def build_adaptive_windows(
    doc_len: int,
    base_window: int = 512,
    base_stride: int = 256,
    short_window_cap: int = 256,
) -> list[tuple[int, int]]:
    """根据文档长度自适应生成滑动窗口列表。

    策略说明：
    - **长文档** (``doc_len > base_window``): 使用固定的 ``base_window`` 和 ``base_stride``。
    - **短文档**: 自动缩小窗口，保证至少 75% 覆盖，并增加重叠。
    - **极短文档** (``doc_len <= 1``): 直接返回单个覆盖窗口。

    Args:
        doc_len: 文档的总词数。
        base_window: 长文档的基础窗口大小。
        base_stride: 长文档的滑动步长。
        short_window_cap: 短文档窗口大小的上限。

    Returns:
        窗口列表，每个元素为 ``(start, end)`` 的半开区间元组。

    Raises:
        ValueError: 当 doc_len 为负数或窗口/步长参数不合法时。
    """
    if doc_len < 0:
        raise ValueError(f"doc_len must be non-negative, got {doc_len}")
    if base_window <= 0 or base_stride <= 0:
        raise ValueError("base_window and base_stride must be positive")
    if base_stride >= base_window:
        logger.warning(
            "base_stride (%d) >= base_window (%d), windows may not cover full document",
            base_stride,
            base_window,
        )

    # 极端情况：空文档或单词文档
    if doc_len <= 1:
        return [(0, max(doc_len, 0))]

    # 确定窗口大小和步长
    if doc_len > base_window:
        win_size = base_window
        stride = base_stride
    else:
        win_size = min(short_window_cap, doc_len)
        if win_size >= doc_len and doc_len > 2:
            win_size = max(2, int(np.ceil(doc_len * 0.75)))
        stride = max(1, win_size // 2)

    # 窗口能覆盖整篇文档
    if win_size >= doc_len:
        return [(0, doc_len)]

    # 生成滑动起始点
    starts = list(range(0, doc_len - win_size + 1, stride))
    last_start = doc_len - win_size
    if starts[-1] != last_start:
        starts.append(last_start)

    # 确保至少两个窗口以获得更好的覆盖
    if len(starts) < 2 and doc_len > win_size:
        mid_start = (doc_len - win_size) // 2
        starts.append(mid_start)
        starts = sorted(set(starts))

    return [(s, s + win_size) for s in starts]


# ======================== 边界解码 ========================


def decode_boundary_from_scores(score_sum: np.ndarray) -> int:
    """通过前缀和方式寻找最优分割边界点。

    算法思路：
        遍历所有可能的分割位置 k，目标函数为::

            objective[k] = sum(-score[:k+1]) + sum(score[k+1:])

        即左侧尽可能多为负分（negative），右侧尽可能多为正分（positive）。

    Args:
        score_sum: 每个词的累积得分数组，正值表示倾向于 positive，
            负值表示倾向于 negative。

    Returns:
        最优边界索引 (0-indexed)。边界左侧（含）标为 negative，右侧标为 positive。
    """
    n = len(score_sum)
    if n <= 0:
        return 0

    prefix_neg = np.cumsum(-score_sum)
    prefix_pos = np.cumsum(score_sum)
    total_pos = prefix_pos[-1]

    # objective[k] = prefix_neg[k] + (total_pos - prefix_pos[k])
    objective = prefix_neg + (total_pos - prefix_pos)
    best_boundary: int = int(np.argmax(objective))

    return max(0, min(best_boundary, n - 1))


def _labels_from_boundary(doc_len: int, boundary: int) -> list[int]:
    """根据边界索引生成词级别的标签列表。

    Args:
        doc_len: 文档总词数。
        boundary: 分割边界索引，``boundary`` 及之前标为 negative，之后标为 positive。

    Returns:
        长度为 ``doc_len`` 的标签列表。
    """
    return [
        LABEL_NEGATIVE if i <= boundary else LABEL_POSITIVE
        for i in range(doc_len)
    ]


# ======================== 推理引擎内部函数 ========================


def _run_single_window(
    model: DeBERTaCRFTagger,
    tokenizer: Any,
    window_words: list[str],
    max_len: int,
    device: torch.device,
) -> tuple[Any, list[int]]:
    """对单个窗口执行 tokenizer 编码 + 模型推理。

    Args:
        model: 已加载权重的 DeBERTaCRFTagger 模型。
        tokenizer: HuggingFace tokenizer 实例。
        window_words: 当前窗口的词列表。
        max_len: tokenizer 最大序列长度。
        device: 推理设备。

    Returns:
        ``(encoding, pred_ids)`` 元组，其中 encoding 为 tokenizer 输出，
        pred_ids 为子词级别的预测标签列表。
    """
    encoding = tokenizer(
        window_words,
        is_split_into_words=True,
        max_length=max_len,
        padding="max_length",
        truncation=True,
        return_tensors="pt",
        return_special_tokens_mask=True,
    )
    input_ids: torch.Tensor = encoding["input_ids"].to(device)
    attention_mask: torch.Tensor = encoding["attention_mask"].to(device)

    predictions = model.predict(input_ids, attention_mask)
    pred_ids: list[int] = predictions[0].detach().cpu().tolist()
    return encoding, pred_ids


def _aggregate_votes(
    word_preds: list[int],
    window_start: int,
    doc_len: int,
    vote_counts: np.ndarray,
    score_sum: np.ndarray,
) -> None:
    """将单个窗口的词级别预测结果累加到全局投票计数和分数中。

    Args:
        word_preds: 当前窗口的词级别预测标签列表。
        window_start: 当前窗口在文档中的起始词索引。
        doc_len: 文档总词数。
        vote_counts: 全局投票计数矩阵 ``(doc_len, 2)``，原地修改。
        score_sum: 全局累积得分数组 ``(doc_len,)``，原地修改。
    """
    num_preds = min(len(word_preds), doc_len - window_start)
    if num_preds <= 0:
        return

    preds_array = np.array(word_preds[:num_preds], dtype=np.int32)
    global_indices = np.arange(window_start, window_start + num_preds)

    # 向量化投票
    valid_mask = global_indices < doc_len
    valid_indices = global_indices[valid_mask]
    valid_preds = preds_array[valid_mask]

    # 更新 vote_counts
    vote_counts[valid_indices, valid_preds] += 1

    # 更新 score_sum: positive → +1.0, negative → -1.0
    scores = np.where(valid_preds == LABEL_POSITIVE, 1.0, -1.0).astype(np.float32)
    score_sum[valid_indices] += scores


# ======================== 公开推理接口 ========================


def infer_document_with_sliding_windows(
    model: DeBERTaCRFTagger,
    words: list[str],
    tokenizer: Any,
    max_len: int | None = None,
    device: torch.device | str | None = None,
    base_window: int = 512,
    base_stride: int = 256,
    short_window_cap: int = 256,
    config: InferenceConfig | None = None,
) -> tuple[list[int], int, np.ndarray]:
    """使用滑动窗口策略对整篇文档进行推理。

    本函数将长文档切分为多个重叠窗口，对每个窗口独立推理后，
    通过多数投票和前缀和边界解码得到全局预测结果。

    支持两种调用方式：

    1. **独立参数**::

        labels, boundary, votes = infer_document_with_sliding_windows(
            model, words, tokenizer, max_len=512, device="cuda",
        )

    2. **配置对象**（优先）::

        cfg = InferenceConfig(max_len=512, device=torch.device("cuda"))
        labels, boundary, votes = infer_document_with_sliding_windows(
            model, words, tokenizer, config=cfg,
        )

    Args:
        model: 已加载权重的 DeBERTaCRFTagger 模型。
        words: 文档的词列表。
        tokenizer: HuggingFace tokenizer 实例。
        max_len: tokenizer 最大序列长度（若提供 config 则忽略）。
        device: 推理设备（若提供 config 则忽略）。
        base_window: 长文档基础窗口大小。
        base_stride: 长文档滑动步长。
        short_window_cap: 短文档窗口上限。
        config: 可选的 InferenceConfig 配置对象，提供时覆盖上述独立参数。

    Returns:
        ``(pred_word_labels, boundary, vote_counts)`` 三元组：

        - **pred_word_labels** (*list[int]*): 词级别标签列表。
        - **boundary** (*int*): 最优分割边界索引。
        - **vote_counts** (*np.ndarray*): 投票计数矩阵，形状 ``(doc_len, 2)``。

    Raises:
        ValueError: 当必要参数缺失或不合法时。
    """
    # ---------- 参数解析 ----------
    if config is not None:
        max_len = config.max_len
        device = config.device
        base_window = config.base_window
        base_stride = config.base_stride
        short_window_cap = config.short_window_cap

    if max_len is None or max_len <= 0:
        raise ValueError(f"max_len must be a positive integer, got {max_len}")
    if device is None:
        device = torch.device("cpu")
    elif isinstance(device, str):
        device = torch.device(device)

    # ---------- 边界情况 ----------
    if not words:
        logger.warning("infer_document_with_sliding_windows received empty word list")
        return [], 0, np.zeros(0, dtype=np.int32)

    doc_len = len(words)

    # ---------- 构建窗口 ----------
    windows = build_adaptive_windows(
        doc_len,
        base_window=base_window,
        base_stride=base_stride,
        short_window_cap=short_window_cap,
    )
    logger.info("Inference: doc_len=%d, num_windows=%d", doc_len, len(windows))

    # ---------- 滑窗推理 ----------
    vote_counts = np.zeros((doc_len, NUM_BINARY_LABELS), dtype=np.int32)
    score_sum = np.zeros(doc_len, dtype=np.float32)

    with torch.no_grad():
        for win_idx, (start, end) in enumerate(windows):
            window_words = words[start:end]
            encoding, pred_ids = _run_single_window(
                model, tokenizer, window_words, max_len, device,
            )
            word_preds = decode_window_word_predictions(encoding, pred_ids)
            _aggregate_votes(word_preds, start, doc_len, vote_counts, score_sum)

            logger.debug(
                "Window %d [%d:%d] processed, %d word-level predictions",
                win_idx,
                start,
                end,
                len(word_preds),
            )

    # ---------- 解码边界 ----------
    boundary = decode_boundary_from_scores(score_sum)
    pred_word_labels = _labels_from_boundary(doc_len, boundary)

    logger.info("Inference complete: boundary=%d, doc_len=%d", boundary, doc_len)
    return pred_word_labels, boundary, vote_counts