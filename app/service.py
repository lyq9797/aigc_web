from __future__ import annotations

import time
from typing import Any, Optional, List, Dict
from dataclasses import dataclass

from .detectors.sentence_level import SentenceLevelDetector
from .detectors.word_level import WordLevelDetector


# =========================
# Result Models
# =========================

@dataclass
class DetectionResult:
    """检测结果数据类"""
    sentences: List[Dict[str, Any]]
    words: List[Dict[str, Any]]
    summary: Dict[str, Any]
    processing_time_ms: float
    text_length: int
    word_count: int
    sentence_count: int


# =========================
# Detection Service
# =========================

class DetectionService:
    """文本检测服务，整合词级别和句子级别检测器"""

    def __init__(self) -> None:
        """初始化检测器实例"""
        self.word_detector = WordLevelDetector()
        self.sentence_detector = SentenceLevelDetector()
        self._cache: Dict[str, DetectionResult] = {}  # 简单缓存
        self._cache_max_size = 100

    # =========================
    # Private Methods
    # =========================

    def _get_cache_key(self, text: str) -> str:
        """生成缓存键"""
        return str(hash(text))[-20:]

    def _cache_result(self, key: str, result: DetectionResult) -> None:
        """缓存检测结果"""
        if len(self._cache) >= self._cache_max_size:
            # 删除最早的条目
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        self._cache[key] = result

    def _predict_sentence(self, text: str) -> Any:
        """执行句子级别检测"""
        return self.sentence_detector.predict(text)

    def _predict_sentence_with_fallback(self, text: str, sent_res: Any) -> Any:
        """
        句子检测降级处理
        当检测器使用fallback模式时，先用词检测器获取粗粒度结果再重新检测
        """
        if sent_res.model_used == "fallback-no-word-signal":
            coarse_word = self.word_detector.predict(text)
            return self.sentence_detector.predict(text, coarse_word.words)
        return sent_res

    def _predict_word(self, text: str, sentences: list[Any]) -> Any:
        """执行词级别检测，传入句子结构辅助判断"""
        return self.word_detector.predict_with_sentence_switches(text, sentences)

    def _build_summary(self, sent_res: Any, word_res: Any, start_time: float) -> dict[str, Any]:
        """构建检测摘要信息"""
        processing_time_ms = (time.time() - start_time) * 1000
        return {
            "word_model": word_res.model_used,
            "sentence_model": sent_res.model_used,
            "switch_word_index": word_res.switch_word_index,
            "switch_sentence_index": sent_res.switch_sentence_index,
            "fallback_used": sent_res.model_used != "fallback-no-word-signal",
            "processing_time_ms": round(processing_time_ms, 2),
        }

    def _validate_result(self, sent_res: Any, word_res: Any) -> None:
        """验证检测结果格式是否正确"""
        if not isinstance(sent_res.sentences, list):
            raise ValueError("句子检测结果格式错误")
        if not isinstance(word_res.words, list):
            raise ValueError("词检测结果格式错误")

    def _count_words(self, words: List[Dict]) -> int:
        """统计单词数量"""
        return len(words)

    def _count_sentences(self, sentences: List[Dict]) -> int:
        """统计句子数量"""
        return len(sentences)

    # =========================
    # Public API
    # =========================

    def detect(self, text: str, use_cache: bool = True) -> dict[str, Any]:
        """
        执行完整检测流程

        Args:
            text: 待检测文本
            use_cache: 是否使用缓存

        Returns:
            包含句子、词和摘要信息的检测结果
        """
        # 参数校验
        if not text or not text.strip():
            raise ValueError("检测文本不能为空")

        # 检查缓存
        cache_key = self._get_cache_key(text)
        if use_cache and cache_key in self._cache:
            cached = self._cache[cache_key]
            return {
                "summary": cached.summary,
                "sentences": cached.sentences,
                "words": cached.words,
            }

        start_time = time.time()

        # 执行检测
        sent_res = self._predict_sentence(text)
        sent_res = self._predict_sentence_with_fallback(text, sent_res)
        word_res = self._predict_word(text, sent_res.sentences)
        self._validate_result(sent_res, word_res)

        # 构建结果
        result = {
            "summary": self._build_summary(sent_res, word_res, start_time),
            "sentences": sent_res.sentences,
            "words": word_res.words,
        }

        # 缓存结果
        detection_result = DetectionResult(
            sentences=sent_res.sentences,
            words=word_res.words,
            summary=result["summary"],
            processing_time_ms=result["summary"]["processing_time_ms"],
            text_length=len(text),
            word_count=self._count_words(word_res.words),
            sentence_count=self._count_sentences(sent_res.sentences),
        )
        self._cache_result(cache_key, detection_result)

        return result

    def detect_batch(self, texts: List[str]) -> List[dict[str, Any]]:
        """
        批量检测文本

        Args:
            texts: 待检测文本列表

        Returns:
            检测结果列表
        """
        results = []
        for text in texts:
            try:
                results.append(self.detect(text))
            except Exception as e:
                results.append({
                    "error": str(e),
                    "summary": {},
                    "sentences": [],
                    "words": [],
                })
        return results

    def get_cache_stats(self) -> dict[str, Any]:
        """获取缓存统计信息"""
        return {
            "cache_size": len(self._cache),
            "cache_max_size": self._cache_max_size,
            "enabled": True,
        }

    def clear_cache(self) -> int:
        """清空缓存，返回清空的条目数"""
        count = len(self._cache)
        self._cache.clear()
        return count

    def get_model_info(self) -> dict[str, str]:
        """获取模型信息"""
        return {
            "word_detector": str(type(self.word_detector).__name__),
            "sentence_detector": str(type(self.sentence_detector).__name__),
        }

    def health_check(self) -> dict[str, Any]:
        """健康检查"""
        try:
            test_result = self.detect("这是一个测试", use_cache=False)
            return {
                "status": "healthy",
                "model_loaded": True,
                "test_success": True,
                "model_info": self.get_model_info(),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "model_loaded": False,
                "error": str(e),
            }