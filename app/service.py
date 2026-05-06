"""
AIGC 文本检测核心业务服务层 (Core Detection Service)

"""

from __future__ import annotations

import logging
import time
from typing import Any, TypedDict

from fastapi import HTTPException, status

from .detectors.sentence_level import SentenceLevelDetector
from .detectors.word_level import WordLevelDetector

# 使用模块级 logger，记录模型降级、超时等关键业务事件
logger = logging.getLogger(__name__)


# ==========================================
# 1. 数据结构定义 (Data Structures)
# ==========================================

class DetectionSummary(TypedDict):
    """检测摘要信息"""
    word_model: str
    sentence_model: str
    switch_word_index: int | None
    switch_sentence_index: int | None


class DetectionResult(TypedDict):
    """完整的检测结果契约"""
    summary: DetectionSummary
    sentences: list[dict[str, Any]]
    words: list[dict[str, Any]]


# ==========================================
# 2. 核心服务类 (Core Service Class)
# ==========================================

class DetectionService:
    """
    AIGC 文本检测编排服务。

    【架构说明】
    负责协调句子级 (Sentence-level) 和词级 (Word-level) 检测器，
    通过多阶段推理 (Multi-stage Inference) 提升检测准确率。

    """

    def __init__(self) -> None:
        # 初始化底层检测器（此处会加载模型权重）
        self.word_detector = WordLevelDetector()
        self.sentence_detector = SentenceLevelDetector()

        # 定义单次推理的最大允许时间（秒），超时则触发熔断
        self._max_inference_time = 10.0

    def detect(self, text: str) -> DetectionResult:
        """
        执行完整的 AIGC 文本检测流水线。

        Args:
            text: 经过预处理和长度校验的纯文本。

        Returns:
            包含句子级和词级检测结果的字典。

        Raises:
            HTTPException: 当模型推理超时、OOM 或发生内部错误时抛出 503。
        """
        start_time = time.perf_counter()

        try:
            # ==========================================
            # Step 1: 句子级初步检测 (Sentence-level First)
            # ==========================================
            sent_res = self.sentence_detector.predict(text)

            # ==========================================
            # Step 2: 降级与补偿机制 (Fallback & Refinement)
            # ==========================================

            if sent_res.model_used == "fallback-no-word-signal":
                logger.warning("Sentence model fallback triggered. Executing coarse word-level detection.")
                coarse_word = self.word_detector.predict(text)
                sent_res = self.sentence_detector.predict(text, coarse_word.words)

            # ==========================================
            # Step 3: 词级边界细化 (Word-level Refinement)
            # ==========================================
            # 基于句子级的切换点，进行词级别的精细化检测
            word_res = self.word_detector.predict_with_sentence_switches(
                text, sent_res.sentences
            )

            # 记录推理总耗时，用于监控模型性能衰退
            elapsed = time.perf_counter() - start_time
            logger.info(
                "Detection completed in %.2fs | SentModel: %s | WordModel: %s | TextLen: %d",
                elapsed, sent_res.model_used, word_res.model_used, len(text)
            )

            if elapsed > self._max_inference_time:
                logger.error("CRITICAL: Inference time (%.2fs) exceeded safety threshold!", elapsed)

            # ==========================================
            # Step 4: 组装响应契约 (Assemble Response)
            # ==========================================
            return {
                "summary": {
                    "word_model": word_res.model_used,
                    "sentence_model": sent_res.model_used,
                    "switch_word_index": word_res.switch_word_index,
                    "switch_sentence_index": sent_res.switch_sentence_index,
                },
                "sentences": sent_res.sentences,
                "words": word_res.words,
            }

        except HTTPException:
            # 透传业务层主动抛出的 HTTP 异常
            raise
        except Exception as exc:
            logger.exception("Critical failure during model inference: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI 检测服务暂时不可用，请稍后重试或缩短文本长度。"
            ) from exc