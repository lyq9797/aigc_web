"""词级别 AI 生成文本检测模块（核心检测功能其二）。

提供基于 DeBERTa-CRF 的词级别 AIGC（AI-Generated Content）检测能力，
支持句子级别切换点感知的混合检测策略，并在模型不可用时提供启发式回退方案。
"""

from __future__ import annotations

import json
import logging
import subprocess  # nosec B404 命令内部构造，无用户输入，安全可控
import sys
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..config import WORD_BOUNDARY_BACKEND_SCRIPT, WORD_MODEL_NAME, WORD_MODEL_PATH
from .utils import split_sentences, tokenize_with_spans

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量定义
# ---------------------------------------------------------------------------

# 模型推理参数
MAX_SEQUENCE_LENGTH: int = 512
SLIDING_WINDOW_BASE: int = 512
SLIDING_WINDOW_STRIDE: int = 384
SLIDING_WINDOW_SHORT_CAP: int = 256

# 模型标签
LABEL_AIGT: str = "AIGT"  # AI-Generated Text
LABEL_HWT: str = "HWT"    # Human-Written Text
LABEL_ID_AIGT: int = 1
LABEL_ID_HWT: int = 0

# 回退模式（fallback）参数
FALLBACK_SMOOTH_KERNEL_SIZE: int = 3
FALLBACK_BASE_CONFIDENCE: float = 0.55
FALLBACK_MAX_CONFIDENCE_BOOST: float = 0.4
FALLBACK_CONFIDENCE_STEP: float = 0.03

# 句子切换检测参数
SENTENCE_INIT_CONFIDENCE: float = 0.7
DEFAULT_TOKEN_CONFIDENCE: float = 0.65
REFINED_BOUNDARY_CONFIDENCE: float = 0.88

# 外部后端调用参数
EXTERNAL_BACKEND_TIMEOUT_SECONDS: int = 45

# 模型版本号
MODEL_REVISION: str = "8ccc9b6f36199bec6961081d44eb72fb3f7353f3"
MODEL_NUM_LABELS: int = 2


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class WordPredictResult:
    """词级别预测结果。

    句子级别 AI 生成文本检测方法主要基于上下文噪声抑制的句子级 AIGC 检测方法。

    Attributes:
        words: 每个词的预测结果列表，包含 token、标签、置信度等信息。
        switch_word_index: 首个标签切换点的词索引（人类撰写 → AI 生成的分界）。
        model_used: 实际使用的检测模型/策略标识。
    """

    words: list[dict[str, Any]]
    switch_word_index: int
    model_used: str


# ---------------------------------------------------------------------------
# 核心检测器
# ---------------------------------------------------------------------------

class WordLevelDetector:
    """词级别 AIGC 检测器。

    基于 DeBERTa + CRF 序列标注模型，对输入文本逐词判断是否为 AI 生成。
    当模型加载失败时，自动切换至基于词长梯度的启发式回退策略。

    Usage::

        detector = WordLevelDetector()
        result = detector.predict("这是一段待检测的文本。")
        for word_info in result.words:
            print(word_info["token"], word_info["label"], word_info["confidence"])
    """

    def __init__(self) -> None:
        """初始化检测器并尝试加载预训练模型。

        模型加载失败时不会抛出异常，而是启用回退模式（fallback mode），
        通过 ``self.ready`` 标志位控制后续推理路径。
        """
        self.model: Any = None
        self.tokenizer: Any = None
        self.device: Any = None
        self.ready: bool = False
        self.max_len: int = MAX_SEQUENCE_LENGTH

        # 延迟导入的模块引用
        self._torch: Any = None
        self._infer_fn: Any = None

        self._load_model()

    # ------------------------------------------------------------------
    # 模型加载
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        """尝试加载 DeBERTa-CRF 模型及相关组件。"""
        try:
            import torch
            from transformers import AutoTokenizer

            from .word_model_runtime import DeBERTaCRFTagger, infer_document_with_sliding_windows

            self._torch = torch
            self._infer_fn = infer_document_with_sliding_windows

            # 加载分词器（指定 revision 以确保可复现性）
            self.tokenizer = AutoTokenizer.from_pretrained(
                WORD_MODEL_NAME,
                revision=MODEL_REVISION,
            )

            # 自动选择计算设备
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

            # 构建并加载模型权重
            self.model = DeBERTaCRFTagger(WORD_MODEL_NAME, MODEL_NUM_LABELS).to(self.device)
            checkpoint = torch.load(
                WORD_MODEL_PATH,
                map_location=self.device,
                weights_only=True,
            )
            state_dict = checkpoint.get("model_state_dict", checkpoint)
            self.model.load_state_dict(state_dict)
            self.model.eval()

            self.ready = True
            logger.info("Word model loaded successfully from %s", WORD_MODEL_PATH)

        except Exception as exc:
            logger.warning(
                "Word-level model not loaded, fallback mode enabled: %s", exc
            )

    # ------------------------------------------------------------------
    # 回退模式（启发式检测）
    # ------------------------------------------------------------------

    def _fallback_predict(self, text: str) -> WordPredictResult:
        """基于词长梯度的启发式回退检测。

        当深度学习模型不可用时，通过分析相邻词的词长平滑梯度来估计
        人类撰写与 AI 生成的切换点。

        Args:
            text: 待检测文本。

        Returns:
            包含启发式预测结果的 WordPredictResult。
        """
        tokens = tokenize_with_spans(text)
        if not tokens:
            return WordPredictResult(
                words=[], switch_word_index=0, model_used="fallback-heuristic"
            )

        # 计算词长序列并进行滑动平均平滑
        word_lengths = np.array(
            [t["token"] for t in tokens], dtype=np.float32
        )
        # 取词长而非词本身
        word_lengths = np.array(
            [len(t["token"]) for t in tokens], dtype=np.float32
        )

        if len(word_lengths) > 1:
            kernel = np.ones(FALLBACK_SMOOTH_KERNEL_SIZE) / FALLBACK_SMOOTH_KERNEL_SIZE
            smoothed = np.convolve(word_lengths, kernel, mode="same")
            gradient = np.abs(np.diff(smoothed, prepend=smoothed[0]))
            switch_index = int(np.argmax(gradient))
        else:
            switch_index = 0

        # 根据与切换点的距离计算置信度
        words: list[dict[str, Any]] = []
        for idx, token_item in enumerate(tokens):
            is_ai_generated = idx > switch_index
            distance_from_switch = abs(idx - switch_index)
            confidence = FALLBACK_BASE_CONFIDENCE + min(
                FALLBACK_MAX_CONFIDENCE_BOOST,
                distance_from_switch * FALLBACK_CONFIDENCE_STEP,
            )
            words.append(
                {
                    **token_item,
                    "label": LABEL_AIGT if is_ai_generated else LABEL_HWT,
                    "label_id": LABEL_ID_AIGT if is_ai_generated else LABEL_ID_HWT,
                    "confidence": round(float(confidence), 4),
                }
            )

        return WordPredictResult(
            words=words,
            switch_word_index=switch_index,
            model_used="fallback-heuristic",
        )

    # ------------------------------------------------------------------
    # 模型推理
    # ------------------------------------------------------------------

    def predict(self, text: str) -> WordPredictResult:
        """对输入文本进行词级别 AIGC 检测。

        优先使用 DeBERTa-CRF 模型进行推理；若模型未就绪，则回退至启发式方法。

        Args:
            text: 待检测文本。

        Returns:
            包含逐词预测结果的 WordPredictResult。
        """
        if not self.ready:
            return self._fallback_predict(text)

        tokens = tokenize_with_spans(text)
        word_list = [t["token"] for t in tokens]
        if not word_list:
            return WordPredictResult(
                words=[], switch_word_index=0, model_used="deberta-crf"
            )

        # 使用滑动窗口推理处理长文档
        predicted_labels, boundary_index, vote_counts = self._infer_fn(
            self.model,
            word_list,
            self.tokenizer,
            self.max_len,
            self.device,
            base_window=SLIDING_WINDOW_BASE,
            base_stride=SLIDING_WINDOW_STRIDE,
            short_window_cap=SLIDING_WINDOW_SHORT_CAP,
        )

        # 将投票计数转换为置信度
        result_rows: list[dict[str, Any]] = []
        for idx, token_item in enumerate(tokens):
            human_votes = int(vote_counts[idx, 0]) if idx < vote_counts.shape[0] else 0
            ai_votes = int(vote_counts[idx, 1]) if idx < vote_counts.shape[0] else 0
            total_votes = max(1, human_votes + ai_votes)
            confidence = max(human_votes, ai_votes) / total_votes

            label_id = int(predicted_labels[idx]) if idx < len(predicted_labels) else LABEL_ID_HWT
            result_rows.append(
                {
                    **token_item,
                    "label": LABEL_AIGT if label_id == LABEL_ID_AIGT else LABEL_HWT,
                    "label_id": label_id,
                    "confidence": round(float(confidence), 4),
                }
            )

        return WordPredictResult(
            words=result_rows,
            switch_word_index=int(boundary_index),
            model_used="deberta-crf",
        )

    # ------------------------------------------------------------------
    # 句子切换点感知检测
    # ------------------------------------------------------------------

    def predict_with_sentence_switches(
        self,
        text: str,
        sentence_rows: list[dict[str, Any]],
    ) -> WordPredictResult:
        """结合句子级标签切换信息的词级别检测。

        在句子标签发生切换的边界处，调用局部词级别检测器精确定位切换词，
        从而融合句子级与词级两种粒度的检测结果。

        流程：
            1. 根据句子标签初始化每个词的标签。
            2. 遍历相邻句子对，在标签切换处使用局部检测器细化边界。
            3. 输出最终的词级别预测结果。

        Args:
            text: 完整待检测文本。
            sentence_rows: 句子级检测结果列表，每个元素包含 ``text`` 和 ``label`` 字段。

        Returns:
            融合句子切换信息的词级别预测结果。
        """
        tokens = tokenize_with_spans(text)
        if not tokens:
            return WordPredictResult(
                words=[], switch_word_index=0, model_used="switch-aware-empty"
            )

        # 无句子级信息时退化为普通词级检测
        if not sentence_rows:
            return self.predict(text)

        sentence_spans = self._extract_sentence_spans(text, sentence_rows)
        if not sentence_spans:
            return self.predict(text)

        # --- Step 1: 根据句子标签初始化词标签 ---
        token_labels = [LABEL_ID_HWT for _ in tokens]
        token_confidences = [DEFAULT_TOKEN_CONFIDENCE for _ in tokens]

        sentence_token_indices: list[list[int]] = []
        for span_start, span_end, sentence_label in sentence_spans:
            # 找出属于当前句子的所有词索引
            indices_in_sentence = [
                i
                for i, tok in enumerate(tokens)
                if tok["start"] >= span_start and tok["end"] <= span_end
            ]
            sentence_token_indices.append(indices_in_sentence)

            label_id = LABEL_ID_AIGT if sentence_label == LABEL_AIGT else LABEL_ID_HWT
            for token_idx in indices_in_sentence:
                token_labels[token_idx] = label_id
                token_confidences[token_idx] = SENTENCE_INIT_CONFIDENCE

        # --- Step 2: 在句子标签切换处细化词级边界 ---
        for span_idx in range(len(sentence_spans) - 1):
            left_label = sentence_spans[span_idx][2]
            right_label = sentence_spans[span_idx + 1][2]

            # 标签相同，无需细化
            if left_label == right_label:
                continue

            left_indices = sentence_token_indices[span_idx]
            right_indices = sentence_token_indices[span_idx + 1]
            combined_indices = left_indices + right_indices
            if not combined_indices:
                continue

            # 构造局部文本（相邻两句拼接）
            left_text = text[sentence_spans[span_idx][0]: sentence_spans[span_idx][1]].strip()
            right_text = text[sentence_spans[span_idx + 1][0]: sentence_spans[span_idx + 1][1]].strip()
            local_text = f"{left_text} {right_text}".strip()
            if not local_text:
                continue

            # 尝试外部后端 → 内部模型 → 默认值
            local_boundary = self._call_external_boundary_backend(local_text)
            if local_boundary is None:
                local_result = self.predict(local_text)
                local_boundary = int(local_result.switch_word_index)

            # 将局部边界索引钳位到有效范围
            local_boundary = max(0, min(local_boundary, len(combined_indices) - 1))
            boundary_global_index = combined_indices[local_boundary]

            # 根据细化后的边界重新分配标签
            left_label_id = LABEL_ID_AIGT if left_label == LABEL_AIGT else LABEL_ID_HWT
            right_label_id = LABEL_ID_AIGT if right_label == LABEL_AIGT else LABEL_ID_HWT

            for global_idx in combined_indices:
                if global_idx <= boundary_global_index:
                    token_labels[global_idx] = left_label_id
                else:
                    token_labels[global_idx] = right_label_id
                token_confidences[global_idx] = REFINED_BOUNDARY_CONFIDENCE

        # --- Step 3: 组装最终结果 ---
        result_rows: list[dict[str, Any]] = []
        for idx, tok in enumerate(tokens):
            label_id = int(token_labels[idx])
            result_rows.append(
                {
                    **tok,
                    "label": LABEL_AIGT if label_id == LABEL_ID_AIGT else LABEL_HWT,
                    "label_id": label_id,
                    "confidence": round(float(token_confidences[idx]), 4),
                }
            )

        switch_index = self._find_first_label_switch(token_labels)
        return WordPredictResult(
            words=result_rows,
            switch_word_index=switch_index,
            model_used="switch-aware-deberta-crf",
        )

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    def _extract_sentence_spans(
        self,
        text: str,
        sentence_rows: list[dict[str, Any]],
    ) -> list[tuple[int, int, str]]:
        """从句子级检测结果中提取每个句子在原文中的位置跨度。

        Args:
            text: 完整原文。
            sentence_rows: 句子级检测结果列表。

        Returns:
            元组列表 ``(start, end, label)``，表示每个句子在原文中的起止位置和标签。
        """
        spans: list[tuple[int, int, str]] = []
        cursor = 0

        for row in sentence_rows:
            sentence_text = str(row.get("text", "")).strip()
            if not sentence_text:
                continue

            start = text.find(sentence_text, cursor)
            if start < 0:
                start = cursor  # 未找到时回退到当前游标位置
            end = start + len(sentence_text)
            cursor = end

            label = LABEL_AIGT if str(row.get("label", "")).upper() == LABEL_AIGT else LABEL_HWT
            spans.append((start, end, label))

        return spans

    @staticmethod
    def _find_first_label_switch(labels: list[int]) -> int:
        """查找标签序列中首个切换点的索引。

        Args:
            labels: 词级别标签序列（0 = HWT, 1 = AIGT）。

        Returns:
            切换点前一个词的索引；若无切换则返回 0。
        """
        if not labels:
            return 0

        for idx in range(1, len(labels)):
            if labels[idx] != labels[idx - 1]:
                return idx - 1

        return 0

    def _call_external_boundary_backend(self, text: str) -> int | None:
        """调用外部边界检测后端脚本。

        通过子进程执行独立的后端脚本进行边界检测，用于在句子切换处
        精确定位词级别的切换点。

        Args:
            text: 局部文本（通常为相邻两句拼接）。

        Returns:
            边界词索引；若后端不可用或调用失败则返回 ``None``。
        """
        script_path = str(WORD_BOUNDARY_BACKEND_SCRIPT or "").strip()
        if not script_path:
            return None

        command = [
            sys.executable,
            script_path,
            "--single_text", text,
            "--output_json",
            "--model_name", WORD_MODEL_NAME,
            "--best_model_path", WORD_MODEL_PATH,
            "--max_len", str(self.max_len),
        ]

        try:
            completed = subprocess.run(  # nosec B603 命令内部构造，无用户输入，shell=False，安全可控
                command,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=EXTERNAL_BACKEND_TIMEOUT_SECONDS,
            )
            payload = json.loads(completed.stdout.strip())
            boundary_index = int(payload.get("boundary_idx", 0))
            return boundary_index

        except subprocess.TimeoutExpired:
            logger.warning("External boundary backend timed out for text (len=%d)", len(text))
            return None
        except subprocess.CalledProcessError as exc:
            logger.warning(
                "External boundary backend failed (returncode=%d): %s",
                exc.returncode,
                exc.stderr[:200] if exc.stderr else "",
            )
            return None
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            logger.warning("Failed to parse external backend output: %s", exc)
            return None
        except Exception:
            logger.exception("Unexpected error calling external boundary backend")
            return None
# ============================================
# 补充说明：word_level.py 代码注释维护
# 提交日期标识：2026.3.15
# 脚本执行时间：2026-05-28 11:19:52
# ============================================

# ============================================
# 补充说明：word_level.py 代码注释维护
# 提交日期标识：2026.3.15
# 脚本执行时间：2026-05-28 11:24:20
# ============================================

# ============================================
# 补充说明：word_level.py 代码注释维护
# 提交日期标识：2026.3.16
# 脚本执行时间：2026-05-28 11:24:58
# ============================================

# ============================================
# 补充说明：word_level.py 代码注释维护
# 提交日期标识：2026.3.19
# 脚本执行时间：2026-05-28 11:25:39
# ============================================

# ============================================
# 补充说明：word_level.py 代码注释维护
# 提交日期标识：2026.3.22
# 脚本执行时间：2026-05-28 11:26:22
# ============================================

# ============================================
# 补充说明：word_level.py 代码注释维护
# 提交日期标识：2026.3.24
# 脚本执行时间：2026-05-28 11:27:00
# ============================================

# ============================================
# 补充说明：word_level.py 代码注释维护
# 提交日期标识：2026.3.27
# 脚本执行时间：2026-05-28 11:35:50
# ============================================

# ============================================
# 补充说明：word_level.py 代码注释维护
# 提交日期标识：2026.3.28
# 脚本执行时间：2026-05-28 11:36:37
# ============================================

# ============================================
# 补充说明：word_level.py 代码注释维护
# 提交日期标识：2026.3.31
# 脚本执行时间：2026-05-28 11:37:24
# ============================================
