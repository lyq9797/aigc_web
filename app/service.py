from __future__ import annotations

from typing import Any

from .detectors.sentence_level import SentenceLevelDetector
from .detectors.word_level import WordLevelDetector


class DetectionService:
    def __init__(self) -> None:
        self.word_detector = WordLevelDetector()
        self.sentence_detector = SentenceLevelDetector()

    def _predict_sentence(self, text: str) -> Any:
        sent_res = self.sentence_detector.predict(text)
        if sent_res.model_used == "fallback-no-word-signal":
            coarse_word = self.word_detector.predict(text)
            sent_res = self.sentence_detector.predict(text, coarse_word.words)
        return sent_res

    def _predict_word(self, text: str, sentences: list[Any]) -> Any:
        return self.word_detector.predict_with_sentence_switches(text, sentences)

    def detect(self, text: str) -> dict[str, Any]:
        sent_res = self._predict_sentence(text)
        word_res = self._predict_word(text, sent_res.sentences)

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
