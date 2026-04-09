# word_model_runtime.py — Version 4
# 改动：完整 docstring、支持 InferenceConfig 入参、修复边界 case

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from torchcrf import CRF
from transformers import AutoModel

logger = logging.getLogger(__name__)

# ---------- 常量定义 ----------
LABEL_NEGATIVE = 0
LABEL_POSITIVE = 1
NUM_BINARY_LABELS = 2
IGNORE_INDEX = -100
DEFAULT_DROPOUT = 0.1
PAD_LABEL = 0


@dataclass
class InferenceConfig:
    """滑动窗口推理的配置参数。

    Attributes:
        max_len: tokenizer 最大序列长度。
        base_window: 长文档使用的基础窗口大小（token 数）。
        base_stride: 长文档滑动步长。
        short_window_cap: 短文档窗口上限。
    """
    max_len: int = 512
    base_window: int = 512
    base_stride: int = 256
    short_window_cap: int = 256


class DeBERTaCRFTagger(nn.Module):
    """基于 DeBERTa + CRF 的序列标注模型。

    该模型使用预训练 DeBERTa 作为编码器，接一个线性分类层和 CRF 层，
    用于词级别的二分类任务（如 AI 生成文本检测）。

    Attributes:
        num_labels: 标签类别数。
        deberta: DeBERTa 预训练编码器。
        classifier: 线性分类头。
        crf: 条件随机场层。
    """

    def __init__(self, model_name: str, num_labels: int, dropout_rate: float = DEFAULT_DROPOUT):
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

        self.num_labels = num_labels
        self.deberta = AutoModel.from_pretrained(model_name)
        self.dropout = nn.Dropout(dropout_rate)
        hidden_size: int = self.deberta.config.hidden_size
        self.classifier = nn.Linear(hidden_size, num_labels)
        nn.init.xavier_uniform_(self.classifier.weight)
        nn.init.constant_(self.classifier.bias, 0)
        self.crf = CRF(num_labels, batch_first=True)
        logger.info(
            "DeBERTaCRFTagger initialized: model=%s, labels=%d, dropout=%.2f",
            model_name, num_labels, dropout_rate,
        )

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        labels: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """前向传播。

        Args:
            input_ids: 输入 token ID，形状 (batch, seq_len)。
            attention_mask: 注意力掩码，形状 (batch, seq_len)。
            labels: 可选标签张量，形状 (batch, seq_len)。
                若提供则返回 CRF 负对数似然损失；
                若不提供则返回 CRF 解码后的预测序列。

        Returns:
            训练模式下返回标量 loss 张量；
            推理模式下返回形状 (batch, seq_len) 的预测张量。
        """
        outputs = self.deberta(input_ids, attention_mask=attention_mask)
        sequence_output = self.dropout(outputs.last_hidden_state)
        logits = self.classifier(sequence_output)

        if labels is not None:
            mask = attention_mask.bool()
            crf_labels = labels.clone()
            crf_labels[crf_labels == IGNORE_INDEX] = PAD_LABEL
            loss = -self.crf(logits, crf_labels, mask=mask, reduction="mean")
            return loss

        mask = attention_mask.bool()
        predictions = self.crf.decode(logits, mask=mask)
        padded_predictions: list[list[int]] = []
        for pred in predictions:
            pad_len = attention_mask.size(1) - len(pred)
            padded_predictions.append(pred + [PAD_LABEL] * pad_len)
        return torch.tensor(padded_predictions, device=input_ids.device)


def decode_window_word_predictions(encoding: Any, pred_ids: list[int]) -> list[int]:
    """将子词级别的预测聚合为词级别的预测。

    优先使用 tokenizer 的 word_ids 进行多数投票聚合；
    若 word_ids 不可用，则回退到 special_tokens_mask 过滤方式。

    Args:
        encoding: tokenizer 编码输出（BatchEncoding）。
        pred_ids: 子词级别的预测标签列表。

    Returns:
        词级别的预测标签列表，每个元素为 LABEL_NEGATIVE 或 LABEL_POSITIVE。
    """
    if not pred_ids:
        logger.warning("decode_window_word_predictions received empty pred_ids")
        return []

    attention_mask: list[int] = encoding["attention_mask"][0].tolist()
    pred_ids = pred_ids[: len(attention_mask)]

    word_ids = None
    try:
        word_ids = encoding.word_ids(batch_index=0)
    except (AttributeError, TypeError, IndexError) as exc:
        logger.debug("word_ids() unavailable, falling back to special_tokens_mask: %s", exc)

    # 回退方案：使用 special_tokens_mask
    if word_ids is None:
        special_tokens_mask: list[int] = encoding["special_tokens_mask"][0].tolist()
        word_level_preds: list[int] = []
        for i, is_special in enumerate(special_tokens_mask):
            if attention_mask[i] == 1 and not is_special:
                word_level_preds.append(int(pred_ids[i]))
        return word_level_preds

    # 主方案：基于 word_ids 的多数投票
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

    word_level_preds = []
    for wid in sorted(per_word_votes.keys()):
        votes = per_word_votes[wid]
        word_level_preds.append(
            LABEL_POSITIVE if votes[LABEL_POSITIVE] > votes[LABEL_NEGATIVE] else LABEL_NEGATIVE
        )
    return word_level_preds


def build_adaptive_windows(
    doc_len: int,
    base_window: int = 512,
    base_stride: int = 256,
    short_window_cap: int = 256,
) -> list[tuple[int, int]]:
    """根据文档长度自适应生成滑动窗口列表。

    对于长文档（超过 base_window），使用固定的窗口和步长；
    对于短文档，自动缩小窗口以获得更多上下文重叠。

    Args:
        doc_len: 文档的总词数。
        base_window: 长文档的基础窗口大小。
        base_stride: 长文档的滑动步长。
        short_window_cap: 短文档窗口大小的上限。

    Returns:
        窗口列表，每个元素为 (start, end) 的元组。

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
            base_stride, base_window,
        )

    if doc_len == 0:
        return [(0, 0)]

    # 单词文档直接返回整段
    if doc_len == 1:
        return [(0, 1)]

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

    # 确保至少有两个窗口以获得更好的覆盖
    if len(starts) < 2 and doc_len > win_size:
        mid_start = (doc_len - win_size) // 2
        starts.append(mid_start)
        starts = sorted(set(starts))

    return [(s, s + win_size) for s in starts]


def decode_boundary_from_scores(score_sum: np.ndarray) -> int:
    """通过前缀和方式寻找最优分割边界点。

    算法思路：遍历所有可能的分割位置，使得分割点左侧累积负分最大、
    右侧累积正分最大，从而确定最佳边界。

    Args:
        score_sum: 每个词的累积得分（正=预测为 positive，负=预测为 negative）。

    Returns:
        最优边界索引（0-indexed）。边界左侧（含）为 negative，右侧为 positive。
    """
    n = len(score_sum)
    if n <= 0:
        return 0

    prefix_neg = np.cumsum(-score_sum)
    prefix_pos = np.cumsum(score_sum)
    total_pos = prefix_pos[-1]
    objective = prefix_neg + (total_pos - prefix_pos)
    best_boundary: int = int(np.argmax(objective))
    return max(0, min(best_boundary, n - 1))


def _labels_from_boundary(doc_len: int, boundary: int) -> list[int]:
    """根据边界索引生成词级别的标签列表。

    Args:
        doc_len: 文档总词数。
        boundary: 分割边界索引，boundary 及之前标为 negative，之后标为 positive。

    Returns:
        长度为 doc_len 的标签列表。
    """
    return [LABEL_NEGATIVE if i <= boundary else LABEL_POSITIVE for i in range(doc_len)]


def _run_single_window(
    model: DeBERTaCRFTagger,
    tokenizer: Any,
    window_words: list[str],
    max_len: int,
    device: Any,
) -> tuple[Any, list[int]]:
    """对单个窗口执行 tokenizer + 模型推理。

    Args:
        model: 已加载权重的 DeBERTaCRFTagger 模型。
        tokenizer: HuggingFace tokenizer 实例。
        window_words: 当前窗口的词列表。
        max_len: tokenizer 最大序列长度。
        device: 推理设备。

    Returns:
        (encoding, pred_ids) 元组。
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
    input_ids = encoding["input_ids"].to(device)
    attention_mask = encoding["attention_mask"].to(device)
    predictions = model(input_ids, attention_mask)
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
        word_preds: 当前窗口的词级别预测标签。
        window_start: 当前窗口在文档中的起始词索引。
        doc_len: 文档总词数。
        vote_counts: 全局投票计数矩阵 (doc_len, 2)，原地修改。
        score_sum: 全局累积得分数组 (doc_len,)，原地修改。
    """
    for local_idx, pred in enumerate(word_preds):
        global_idx = window_start + local_idx
        if global_idx < doc_len:
            pred_i = int(pred)
            vote_counts[global_idx, pred_i] += 1
            score_sum[global_idx] += 1.0 if pred_i == LABEL_POSITIVE else -1.0


def infer_document_with_sliding_windows(
    model: DeBERTaCRFTagger,
    words: list[str],
    tokenizer: Any,
    max_len: int | None = None,
    device: Any = None,
    base_window: int = 512,
    base_stride: int = 256,
    short_window_cap: int = 256,
    config: InferenceConfig | None = None,
) -> tuple[list[int], int, np.ndarray]:
    """使用滑动窗口策略对整篇文档进行推理。

    支持两种调用方式：
    1. 传入独立的 max_len / device / base_window 等参数；
    2. 传入一个 InferenceConfig 对象（此时独立参数被忽略）。

    Args:
        model: 已加载权重的 DeBERTaCRFTagger 模型。
        words: 文档的词列表。
        tokenizer: HuggingFace tokenizer 实例。
        max_len: tokenizer 最大序列长度（若提供 config 则忽略）。
        device: 推理设备（若提供 config 则忽略）。
        base_window: 长文档基础窗口大小。
        base_stride: 长文档滑动步长。
        short_window_cap: 短文档窗口上限。
        config: 可选的 InferenceConfig 配置对象。

    Returns:
        (pred_word_labels, boundary, vote_counts) 三元组：
        - pred_word_labels: 词级别标签列表。
        - boundary: 最优分割边界索引。
        - vote_counts: 投票计数矩阵 (doc_len, 2)。

    Raises:
        ValueError: 当参数不合法时。
    """
    # 如果传入了 config 对象，优先使用 config 中的参数
    if config is not None:
        max_len = config.max_len
        device = config.device
        base_window = config.base_window
        base_stride = config.base_stride
        short_window_cap = config.short_window_cap

    if max_len is None or max_len <= 0:
        raise ValueError(f"max_len must be positive, got {max_len}")

    if not words:
        logger.warning("infer_document_with_sliding_windows received empty word list")
        return [], 0, np.zeros(0, dtype=np.int32)

    doc_len = len(words)
    windows = build_adaptive_windows(
        doc_len,
        base_window=base_window,
        base_stride=base_stride,
        short_window_cap=short_window_cap,
    )
    logger.info("Inference: doc_len=%d, num_windows=%d", doc_len, len(windows))

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
                win_idx, start, end, len(word_preds),
            )

    boundary = decode_boundary_from_scores(score_sum)
    pred_word_labels = _labels_from_boundary(doc_len, boundary)
    logger.info("Inference complete: boundary=%d, doc_len=%d", boundary, doc_len)
    return pred_word_labels, boundary, vote_counts