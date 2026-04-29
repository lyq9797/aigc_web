# app/detector/sentence_level.py
"""
句子级别的 AIGT（AI-Generated Text）检测模块。

本模块提供 SentenceLevelDetector 类，用于将文本按句子粒度进行 AI 生成判定。
检测策略按优先级依次为：
    1. 调用外部后端脚本获取结果（支持自动重试）。
    2. 基于词级检测信号按句子聚合判定。
    3. 兜底策略（全部标记为人工撰写 HWT）。
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from typing import Any

from ..config import SENTENCE_BACKEND_SCRIPT
from .utils import split_sentences

logger = logging.getLogger(__name__)


# =============================================================================
# 数据结构
# =============================================================================

@dataclass
class SentencePredictResult:
    """句子级别检测的结果。

    Attributes:
        sentences: 每个句子的检测结果列表。
            每项包含:
                - index (int): 句子序号
                - text (str): 句子原文
                - label (str): "AIGT" 或 "HWT"
                - confidence (float): 置信度，范围 [0.5, 0.99]
                - ai_ratio (float): AI 词占比，范围 [0.0, 1.0]
        switch_sentence_index: 第一个被判定为 AIGT 的句子索引（切换点）。
        model_used: 本次检测使用的模型/策略名称。
    """
    sentences: list[dict[str, Any]]
    switch_sentence_index: int
    model_used: str

    def to_dict(self) -> dict[str, Any]:
        """将结果转换为字典，便于 JSON 序列化。

        Returns:
            包含所有字段的字典。
        """
        return asdict(self)

    def get_summary(self) -> dict[str, Any]:
        """生成检测结果的统计摘要。

        Returns:
            包含总句数、AIGT 句数、HWT 句数、平均置信度、平均 AI 占比的字典。
        """
        total = len(self.sentences)
        if total == 0:
            return {
                "total_sentences": 0,
                "aigt_count": 0,
                "hwt_count": 0,
                "avg_confidence": 0.0,
                "avg_ai_ratio": 0.0,
                "switch_sentence_index": self.switch_sentence_index,
                "model_used": self.model_used,
            }

        aigt_count = sum(1 for s in self.sentences if s.get("label") == "AIGT")
        hwt_count = total - aigt_count
        avg_confidence = sum(s.get("confidence", 0.5) for s in self.sentences) / total
        avg_ai_ratio = sum(s.get("ai_ratio", 0.0) for s in self.sentences) / total

        return {
            "total_sentences": total,
            "aigt_count": aigt_count,
            "hwt_count": hwt_count,
            "avg_confidence": round(avg_confidence, 4),
            "avg_ai_ratio": round(avg_ai_ratio, 4),
            "switch_sentence_index": self.switch_sentence_index,
            "model_used": self.model_used,
        }

    def __repr__(self) -> str:
        return (
            f"SentencePredictResult("
            f"num_sentences={len(self.sentences)}, "
            f"switch_idx={self.switch_sentence_index}, "
            f"model='{self.model_used}')"
        )


# =============================================================================
# 检测器
# =============================================================================

class SentenceLevelDetector:
    """
    句子级别的 AIGT 检测器。

    检测策略优先级：
        1. 调用外部后端脚本（work1_single/test_single_text.py）获取结果。
        2. 如果外部后端不可用，基于词级信号按句子聚合判定。
        3. 如果词级信号也没有，使用兜底策略（全部标为 HWT）。

    Example::

        detector = SentenceLevelDetector()
        result = detector.predict("这是一段测试文本。", words=word_results)
        print(result.get_summary())
    """

    # ---- 外部后端配置 ----
    MAX_RETRIES: int = 2
    RETRY_DELAY: float = 2.0          # 重试间隔（秒）
    BACKEND_TIMEOUT: int = 45         # 外部脚本超时（秒）

    # ---- 置信度计算相关阈值 ----
    CONFIDENCE_FLOOR: float = 0.5     # 最低置信度
    CONFIDENCE_CEIL: float = 0.99     # 最高置信度
    DEFAULT_CONFIDENCE: float = 0.5   # 无词匹配时的默认置信度

    # ---- 标签判定阈值 ----
    AI_RATIO_THRESHOLD: float = 0.5   # AI 词占比 >= 该值则判定为 AIGT

    # ---- 默认 AI ratio ----
    DEFAULT_AI_RATIO_HWT: float = 0.0
    DEFAULT_AI_RATIO_AIGT: float = 1.0

    # ---- 模型名称标识 ----
    MODEL_EXTERNAL: str = "work1-test-single"
    MODEL_AGGREGATED: str = "aggregated-word-signal"
    MODEL_FALLBACK: str = "fallback-no-word-signal"
    MODEL_EMPTY: str = "empty-input"

    def __repr__(self) -> str:
        return (
            f"SentenceLevelDetector("
            f"max_retries={self.MAX_RETRIES}, "
            f"timeout={self.BACKEND_TIMEOUT}s)"
        )

    # -------------------------------------------------------------------------
    # 辅助工厂方法
    # -------------------------------------------------------------------------

    def _make_result(
        self,
        sentences: list[dict[str, Any]],
        model_used: str,
        switch_idx: int | None = None,
    ) -> SentencePredictResult:
        """构造 SentencePredictResult 的统一入口。

        Args:
            sentences: 句子检测结果列表。
            model_used: 使用的模型/策略名称。
            switch_idx: 切换点索引；为 None 时自动计算。

        Returns:
            构造好的 SentencePredictResult。
        """
        if switch_idx is None:
            switch_idx = self._compute_switch_idx(sentences)
        return SentencePredictResult(
            sentences=sentences,
            switch_sentence_index=switch_idx,
            model_used=model_used,
        )

    # -------------------------------------------------------------------------
    # 核心逻辑
    # -------------------------------------------------------------------------

    def _compute_switch_idx(self, sentence_rows: list[dict[str, Any]]) -> int:
        """找到第一个被标记为 AIGT 的句子的索引。

        Args:
            sentence_rows: 句子检测结果列表。

        Returns:
            第一个 AIGT 句子的索引；如果没有 AIGT 句子，返回 0。
        """
        for row in sentence_rows:
            if row.get("label") == "AIGT":
                return int(row.get("index", 0))
        return 0

    def _parse_external_rows(self, rows_raw: list[dict]) -> list[dict[str, Any]]:
        """解析外部后端返回的原始句子数据为标准格式。

        Args:
            rows_raw: 外部后端 JSON 中的 sentences 列表。

        Returns:
            标准化后的句子结果列表。
        """
        rows: list[dict[str, Any]] = []
        for idx, item in enumerate(rows_raw):
            label = str(item.get("label", "HWT")).upper()
            is_ai = (label == "AIGT")
            default_ai_ratio = self.DEFAULT_AI_RATIO_AIGT if is_ai else self.DEFAULT_AI_RATIO_HWT
            rows.append({
                "index": idx,
                "text": str(item.get("text", "")),
                "label": "AIGT" if is_ai else "HWT",
                "confidence": round(float(item.get("confidence", self.DEFAULT_CONFIDENCE)), 4),
                "ai_ratio": round(float(item.get("ai_ratio", default_ai_ratio)), 4),
            })
        return rows

    def _run_external_once(self, cmd: list[str]) -> SentencePredictResult | None:
        """执行一次外部后端调用。

        Args:
            cmd: 要执行的命令行参数列表。

        Returns:
            成功时返回 SentencePredictResult，失败时返回 None。
        """
        completed = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=self.BACKEND_TIMEOUT,
        )

        lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        if not lines:
            logger.warning("外部后端未返回有效输出")
            return None

        payload = json.loads(lines[-1])
        rows = self._parse_external_rows(payload.get("sentences", []))

        if not rows:
            logger.warning("外部后端返回的句子列表为空")
            return None

        logger.info("外部后端成功返回 %d 个句子结果", len(rows))
        return self._make_result(rows, self.MODEL_EXTERNAL,
                                 switch_idx=int(payload.get("switch_sentence_index", -1)) if "switch_sentence_index" in payload else None)

    def _call_external_backend(self, text: str) -> SentencePredictResult | None:
        """调用外部后端脚本进行句子检测（带重试）。

        Args:
            text: 待检测的文本。

        Returns:
            成功时返回 SentencePredictResult，所有重试均失败时返回 None。
        """
        script_path = str(SENTENCE_BACKEND_SCRIPT or "").strip()
        if not script_path:
            logger.info("外部后端脚本路径未配置，跳过外部调用")
            return None

        logger.info("正在调用外部后端脚本: %s", script_path)

        cmd = [
            sys.executable,
            script_path,
            "--single_text",
            text,
            "--output_json",
        ]

        total_attempts = 1 + self.MAX_RETRIES
        for attempt in range(total_attempts):
            try:
                result = self._run_external_once(cmd)
                if result is not None:
                    return result
            except subprocess.TimeoutExpired:
                logger.error("外部后端调用超时（%d秒），第 %d/%d 次尝试",
                             self.BACKEND_TIMEOUT, attempt + 1, total_attempts)
            except subprocess.CalledProcessError as e:
                logger.error("外部后端执行失败，返回码: %d, stderr: %s，第 %d/%d 次尝试",
                             e.returncode, e.stderr, attempt + 1, total_attempts)
            except json.JSONDecodeError:
                logger.error("外部后端返回的JSON解析失败，第 %d/%d 次尝试",
                             attempt + 1, total_attempts)
            except Exception as e:
                logger.error("外部后端调用发生未知异常: %s，第 %d/%d 次尝试",
                             e, attempt + 1, total_attempts)

            if attempt < self.MAX_RETRIES:
                logger.info("等待 %.1f 秒后重试...", self.RETRY_DELAY)
                time.sleep(self.RETRY_DELAY)

        logger.error("外部后端调用在 %d 次尝试后仍然失败", total_attempts)
        return None

    def _build_sentence_offsets(self, text: str, sents: list[str]) -> list[tuple[int, int]]:
        """计算每个句子在原文中的 (start, end) 字符偏移量。

        Args:
            text: 原始文本。
            sents: 分句后的句子列表。

        Returns:
            与 sents 等长的 (start, end) 偏移量列表。
        """
        offsets: list[tuple[int, int]] = []
        cursor = 0
        for sent in sents:
            pos = text.find(sent, cursor)
            if pos < 0:
                pos = cursor
            offsets.append((pos, pos + len(sent)))
            cursor = pos + len(sent)
        return offsets

    def _compute_sentence_ai_score(
        self, within_words: list[dict[str, Any]]
    ) -> tuple[float, float, str]:
        """根据句子内的词级预测结果，计算 AI 占比、置信度和标签。

        Args:
            within_words: 落在当前句子范围内的词级检测结果。

        Returns:
            (ai_ratio, confidence, label) 三元组。
        """
        if not within_words:
            return 0.0, self.DEFAULT_CONFIDENCE, "HWT"

        # 过滤掉缺少必要字段的异常词数据
        valid_words = [w for w in within_words if "label_id" in w]
        if not valid_words:
            return 0.0, self.DEFAULT_CONFIDENCE, "HWT"

        ai_count = sum(1 for w in valid_words if w["label_id"] == 1)
        ai_ratio = ai_count / len(valid_words)
        confidence = max(
            self.CONFIDENCE_FLOOR,
            min(self.CONFIDENCE_CEIL, self.CONFIDENCE_FLOOR + abs(ai_ratio - self.AI_RATIO_THRESHOLD)),
        )
        label = "AIGT" if ai_ratio >= self.AI_RATIO_THRESHOLD else "HWT"

        return ai_ratio, confidence, label

    def _match_words_to_sentences(
        self,
        words: list[dict[str, Any]],
        offsets: list[tuple[int, int]],
    ) -> list[list[dict[str, Any]]]:
        """将词级结果按句子偏移量分配到各句子中。

        先对 words 按 start 排序，然后用双指针扫描，避免对每个句子都遍历全部词。

        Args:
            words: 词级检测结果列表，每项需包含 start, end 字段。
            offsets: 句子的 (start, end) 偏移量列表。

        Returns:
            与 offsets 等长的列表，每项为落入对应句子的词列表。
        """
        # 过滤并排序
        valid_words = sorted(
            [w for w in words if w.get("start") is not None and w.get("end") is not None],
            key=lambda w: w["start"],
        )

        result: list[list[dict[str, Any]]] = [[] for _ in offsets]
        word_idx = 0
        num_words = len(valid_words)

        for sent_idx, (sent_start, sent_end) in enumerate(offsets):
            # 跳过结束位置在当前句子之前的词
            while word_idx < num_words and valid_words[word_idx]["end"] <= sent_start:
                word_idx += 1
            # 收集落在当前句子范围内的词
            scan_idx = word_idx
            while scan_idx < num_words and valid_words[scan_idx]["start"] < sent_end:
                w = valid_words[scan_idx]
                if w["start"] >= sent_start and w["end"] <= sent_end:
                    result[sent_idx].append(w)
                scan_idx += 1

        return result

    def _aggregate_from_words(self, text: str, words: list[dict[str, Any]]) -> SentencePredictResult:
        """基于词级信号聚合生成句子级别检测结果。

        Args:
            text: 待检测的原始文本。
            words: 词级检测结果列表，每项需包含 start, end, label_id 字段。

        Returns:
            句子级别的检测结果。
        """
        if not text or not text.strip():
            logger.info("输入文本为空，返回空结果")
            return self._make_result([], self.MODEL_AGGREGATED, switch_idx=0)

        sents = split_sentences(text)
        if not sents:
            return self._make_result([], self.MODEL_AGGREGATED, switch_idx=0)

        offsets = self._build_sentence_offsets(text, sents)
        words_per_sentence = self._match_words_to_sentences(words, offsets)

        sentence_rows: list[dict[str, Any]] = []
        for idx, sent in enumerate(sents):
            ai_ratio, confidence, label = self._compute_sentence_ai_score(words_per_sentence[idx])
            sentence_rows.append({
                "index": idx,
                "text": sent,
                "label": label,
                "confidence": round(float(confidence), 4),
                "ai_ratio": round(float(ai_ratio), 4),
            })

        return self._make_result(sentence_rows, self.MODEL_AGGREGATED)

    def _fallback_without_words(self, text: str) -> SentencePredictResult:
        """兜底策略：无词级信号时，将所有句子标记为 HWT。

        Args:
            text: 待检测的原始文本。

        Returns:
            所有句子均标记为 HWT 的结果。
        """
        logger.info("使用无词信号的兜底策略")

        if not text or not text.strip():
            return self._make_result([], self.MODEL_FALLBACK, switch_idx=0)

        sents = split_sentences(text)
        rows = [
            {
                "index": idx,
                "text": sent,
                "label": "HWT",
                "confidence": self.DEFAULT_CONFIDENCE,
                "ai_ratio": self.DEFAULT_AI_RATIO_HWT,
            }
            for idx, sent in enumerate(sents)
        ]
        return self._make_result(rows, self.MODEL_FALLBACK, switch_idx=0)

    # -------------------------------------------------------------------------
    # 公开接口
    # -------------------------------------------------------------------------

    def predict(self, text: str, words: list[dict[str, Any]] | None = None) -> SentencePredictResult:
        """执行句子级别的 AIGT 检测。

        按优先级依次尝试：外部后端 → 词级聚合 → 兜底策略。

        Args:
            text: 待检测的文本字符串。
            words: 可选的词级检测结果列表。如果提供，当外部后端不可用时
                   将基于词级信号进行句子聚合。每项应包含:
                   - start (int): 词在原文中的起始位置
                   - end (int): 词在原文中的结束位置
                   - label_id (int): 1 表示 AI 生成，0 表示人工撰写

        Returns:
            SentencePredictResult 对象，包含每个句子的检测结果和切换点索引。
            可通过 to_dict() 序列化，或通过 get_summary() 获取统计摘要。
        """
        # ---- 输入校验 ----
        if not isinstance(text, str):
            logger.warning("predict 收到非字符串类型输入: %s，转为空字符串处理", type(text))
            text = ""

        if not text.strip():
            logger.info("输入文本为空，直接返回空结果")
            return self._make_result([], self.MODEL_EMPTY, switch_idx=0)

        logger.info("开始句子级别检测，文本长度: %d", len(text))

        # 策略1：尝试外部后端
        external = self._call_external_backend(text)
        if external is not None:
            logger.info("使用外部后端结果，模型: %s", external.model_used)
            return external

        # 策略2：基于词级信号聚合
        if words is not None:
            logger.info("使用词级信号聚合策略，词数: %d", len(words))
            return self._aggregate_from_words(text, words)

        # 策略3：兜底
        return self._fallback_without_words(text)