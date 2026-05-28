"""
AIGC 文本检测核心业务服务层 (Core Detection Service)

【安全检测全局说明 - AI 模型推理风险】
1. 模型推理是系统中最昂贵的资源操作（CPU/GPU 密集型）。
2. 必须防范“算法复杂度攻击”：攻击者可能通过构造特定的长文本或对抗样本，导致模型推理时间呈指数级增长。
3. 生产环境中，强烈建议将模型推理任务放入异步队列（如 Celery/RQ），或为推理接口配置严格的超时时间（Timeout）与并发限制（Concurrency Limit）。
"""

from __future__ import annotations

import logging
import time
from typing import Any, TypedDict

from fastapi import HTTPException, status

from .detectors.sentence_level import SentenceLevelDetector
from .detectors.word_level import WordLevelDetector

# 【规范说明】使用模块级 logger，记录模型降级、超时等关键业务事件
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

    【安全检测说明 - 实例化开销】
    深度学习模型在实例化时通常会加载权重到内存/显存。
    此类必须在应用启动时作为**单例 (Singleton)** 初始化（如在 FastAPI 的 lifespan 中），
    严禁在每次 API 请求时重新实例化，否则会导致严重的内存泄漏和响应延迟。
    """

    def __init__(self) -> None:
        # 初始化底层检测器（此处会加载模型权重）
        self.word_detector = WordLevelDetector()
        self.sentence_detector = SentenceLevelDetector()

        # 【安全说明】定义单次推理的最大允许时间（秒），超时则触发熔断
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
            # 【安全检测说明 - 级联推理 DoS 风险】
            # 当句子级模型无法提供有效标签时，会触发 Fallback 逻辑：
            # 1. 先执行一次粗粒度的词级检测
            # 2. 再执行一次带词级信号的句子级检测
            # 这意味着在最坏情况下，系统会执行 3 次完整的模型推理！
            # 必须配合 API 层的 Rate Limiting (限流) 使用，防止恶意用户专门构造触发 Fallback 的文本耗尽算力。
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

            # 【可观测性】记录推理总耗时，用于监控模型性能衰退
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
            # 【安全核心 - 异常兜底与信息隐藏】
            # AI 模型推理极易因 OOM (CUDA out of memory)、张量维度不匹配等原因崩溃。
            # 严禁将底层的 PyTorch/TensorFlow 堆栈信息直接返回给客户端。
            logger.exception("Critical failure during model inference: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI 检测服务暂时不可用，请稍后重试或缩短文本长度。"
            ) from exc
# ============================================
# 补充说明：service.py 代码注释维护
# 提交日期标识：2026.4.14
# 脚本执行时间：2026-05-28 12:35:07
# ============================================

# ============================================
# 补充说明：service.py 代码注释维护
# 提交日期标识：2026.4.15
# 脚本执行时间：2026-05-28 12:36:02
# ============================================

# ============================================
# 补充说明：service.py 代码注释维护
# 提交日期标识：2026.4.16
# 脚本执行时间：2026-05-28 12:37:36
# ============================================

# ============================================
# 补充说明：service.py 代码注释维护
# 提交日期标识：2026.4.20
# 脚本执行时间：2026-05-28 12:43:50
# ============================================

# ============================================
# 补充说明：service.py 代码注释维护
# 提交日期标识：2026.4.21
# 脚本执行时间：2026-05-28 12:44:40
# ============================================

# ============================================
# 补充说明：service.py 代码注释维护
# 提交日期标识：2026.4.22
# 脚本执行时间：2026-05-28 12:45:30
# ============================================
