from __future__ import annotations

from typing import Any

from .detectors.sentence_level import SentenceLevelDetector
from .detectors.word_level import WordLevelDetector


class DetectionService:
    def __init__(self) -> None:
        self.word_detector = WordLevelDetector()
        self.sentence_detector = SentenceLevelDetector()

    def _predict_sentence(self, text: str) -> Any:
        return self.sentence_detector.predict(text)

    def _predict_sentence_with_fallback(self, text: str, sent_res: Any) -> Any:
        if sent_res.model_used == "fallback-no-word-signal":
            coarse_word = self.word_detector.predict(text)
            return self.sentence_detector.predict(text, coarse_word.words)
        return sent_res

    def _predict_word(self, text: str, sentences: list[Any]) -> Any:
        return self.word_detector.predict_with_sentence_switches(text, sentences)

    def _build_summary(self, sent_res: Any, word_res: Any) -> dict[str, Any]:
        return {
            "word_model": word_res.model_used,
            "sentence_model": sent_res.model_used,
            "switch_word_index": word_res.switch_word_index,
            "switch_sentence_index": sent_res.switch_sentence_index,
            "fallback_used": sent_res.model_used != "fallback-no-word-signal",
        }

    def _validate_result(self, sent_res: Any, word_res: Any) -> None:
        if not isinstance(sent_res.sentences, list) or not isinstance(word_res.words, list):
            raise ValueError("模型输出格式不符合预期")

    def detect(self, text: str) -> dict[str, Any]:
        sent_res = self._predict_sentence(text)
        sent_res = self._predict_sentence_with_fallback(text, sent_res)
        word_res = self._predict_word(text, sent_res.sentences)
        self._validate_result(sent_res, word_res)

        return {
            "summary": self._build_summary(sent_res, word_res),
            "sentences": sent_res.sentences,
            "words": word_res.words,
        }
