from abc import ABC, abstractmethod
from typing import Any


class SemanticAnalyzer(ABC):
    """Stable interface for Phase 4 local embeddings, optional LLM, or heuristics."""

    version: str

    @abstractmethod
    def segment_topics(self, transcript_units: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raise NotImplementedError


class HeuristicAnalyzer(SemanticAnalyzer):
    version = "heuristic-v1"

    def segment_topics(self, transcript_units: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return []
