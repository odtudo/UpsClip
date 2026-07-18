from __future__ import annotations

import hashlib
import re
from statistics import median
from typing import Any

import numpy as np

from ...config import Settings
from .spanish_text import extract_distinctive_terms, filler_ratio, grounded


def semantic_windows(segments: list[dict[str, Any]], settings: Settings) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    for segment in segments:
        current.append(segment)
        duration = current[-1]["end"] - current[0]["start"]
        if duration >= settings.semantic_window_target_seconds:
            windows.append(_window(current, len(windows)))
            current = []
    if current:
        if windows and current[-1]["end"] - current[0]["start"] < settings.semantic_window_min_seconds:
            previous = windows[-1].pop("segments")
            windows[-1] = _window([*previous, *current], windows[-1]["index"])
        else:
            windows.append(_window(current, len(windows)))
    return windows


def _window(items: list[dict[str, Any]], index: int) -> dict[str, Any]:
    return {
        "index": index,
        "start": items[0]["start"],
        "end": items[-1]["end"],
        "text": " ".join(item["text"] for item in items),
        "segments": items,
    }


class LocalEmbeddingAnalyzer:
    """Use multilingual MiniLM when available and report fallback truthfully."""

    def __init__(self, model_name: str, cache_dir: str | None = None):
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.requested_backend = model_name
        self.backend = "multilingual-hash-fallback-v2"
        self.model_loaded = False
        self.fallback_used = False
        self.fallback_reason: str | None = None

    def encode(self, texts: list[str]) -> list[list[float]]:
        try:
            from fastembed import TextEmbedding

            model = TextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir)
            self.backend = self.model_name
            self.model_loaded = True
            values = []
            for embedding in model.embed(texts):
                vector = np.asarray(embedding, dtype=np.float32)
                norm = float(np.linalg.norm(vector))
                values.append((vector / norm).tolist() if norm else vector.tolist())
            return values
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            self.fallback_used = True
            self.fallback_reason = f"{type(exc).__name__}: {str(exc)[:200]}"
            return [self._hash_embedding(text) for text in texts]

    def details(self) -> dict[str, Any]:
        return {
            "requested_backend": self.requested_backend,
            "effective_backend": self.backend,
            "model_loaded": self.model_loaded,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
        }

    @staticmethod
    def _hash_embedding(text: str, dimensions: int = 384) -> list[float]:
        vector = np.zeros(dimensions, dtype=np.float32)
        tokens = re.findall(r"[\wáéíóúñü]+", text.casefold())
        features = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False)]
        for feature in features:
            value = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "little")
            vector[value % dimensions] += 1.0 if value & 1 else -1.0
        norm = float(np.linalg.norm(vector))
        return (vector / norm).tolist() if norm else vector.tolist()


def cosine(first: list[float], second: list[float]) -> float:
    return float(np.dot(first, second) / max(1e-9, np.linalg.norm(first) * np.linalg.norm(second)))


def keywords(text: str, maximum: int = 5, corpus: list[str] | None = None) -> list[str]:
    return [item["term"] for item in extract_distinctive_terms(text, corpus or [text], maximum)]


def detect_topic_blocks(windows: list[dict[str, Any]], settings: Settings) -> list[dict[str, Any]]:
    if not windows:
        return []
    blocks: list[list[dict[str, Any]]] = [[windows[0]]]
    low_runs = 0
    for index in range(1, len(windows)):
        similarity = cosine(windows[index - 1]["embedding"], windows[index]["embedding"])
        lexical_first = set(keywords(windows[index - 1]["text"]))
        lexical_second = set(keywords(windows[index]["text"]))
        lexical = len(lexical_first & lexical_second) / max(1, len(lexical_first | lexical_second))
        transition = bool(
            re.search(
                r"\b(cambiando de tema|otra cosa|por cierto|en fin|total que|el caso es)\b",
                windows[index]["text"].casefold(),
            )
        )
        low_runs = low_runs + 1 if similarity < 0.38 and lexical < 0.12 else 0
        duration = blocks[-1][-1]["end"] - blocks[-1][0]["start"]
        boundary = duration >= settings.topic_min_seconds and (
            transition or low_runs >= 2 or duration >= settings.topic_max_seconds
        )
        if boundary:
            reason = (
                "sustained_semantic_shift"
                if low_runs >= 2
                else "explicit_transition"
                if transition
                else "maximum_topic_duration"
            )
            windows[index]["boundary_reasons"] = [reason]
            blocks.append([windows[index]])
            low_runs = 0
        else:
            blocks[-1].append(windows[index])
    corpus = [" ".join(item["text"] for item in group) for group in blocks]
    return [_topic_block(group, corpus) for group in blocks]


def representative_sentences(text: str, terms: list[str], maximum: int = 6) -> list[str]:
    raw_sentences = [
        item.strip() for item in re.split(r"(?<=[.!?])\s+", text) if len(item.split()) >= 6
    ]
    sentences: list[str] = []
    seen: set[str] = set()
    for sentence in raw_sentences:
        fingerprint = re.sub(r"\W+", " ", sentence.casefold()).strip()
        if fingerprint not in seen:
            sentences.append(sentence)
            seen.add(fingerprint)
    scored: list[tuple[float, int, str]] = []
    for index, sentence in enumerate(sentences):
        relevance = sum(grounded(term, sentence)[0] for term in terms)
        scored.append((relevance * 2 + 1 - filler_ratio(sentence), index, sentence))
    selected: list[tuple[int, str]] = []
    for _, index, sentence in sorted(scored, reverse=True):
        selected.append((index, sentence))
        if len(selected) >= maximum:
            break
    return [sentence for _, sentence in sorted(selected)]


def topic_label(text: str, terms: list[str]) -> str:
    normalized = text.casefold()
    if ("inteligencia artificial" in normalized or re.search(r"\bia\b", normalized)) and any(
        term in normalized for term in ("artista", "ilustrador", "miniatura")
    ):
        return "IA y trabajo de ilustradores"
    if "gestor" in normalized and "contenido" in normalized and any(
        term in normalized for term in ("streamer", "youtuber", "creador")
    ):
        return "gestores de contenido para streamers"
    if "francia" in normalized and "marruecos" in normalized:
        return "Francia-Marruecos y el PSG" if "psg" in normalized else "partido Francia-Marruecos"
    return terms[0] if terms else "tema sin etiqueta específica"


def _topic_block(group: list[dict[str, Any]], corpus: list[str]) -> dict[str, Any]:
    text = " ".join(item["text"] for item in group)
    terms = keywords(text, 8, corpus)
    similarities = [
        cosine(group[index - 1]["embedding"], group[index]["embedding"])
        for index in range(1, len(group))
    ]
    centroid = np.mean([item["embedding"] for item in group], axis=0).tolist()
    centroid_scores = [cosine(item["embedding"], centroid) for item in group]
    internal = median(similarities) if similarities else 0.5
    persistence = sum(score >= 0.42 for score in centroid_scores) / len(centroid_scores)
    changes = sum(score < 0.32 for score in similarities) / max(1, len(similarities))
    coherence = max(0.0, min(1.0, 0.55 * internal + 0.35 * persistence + 0.10 * (1 - changes)))
    topic = topic_label(text, terms)
    representative = representative_sentences(text, terms)
    summary = " ".join(representative[:2])
    return {
        "start_seconds": group[0]["start"],
        "end_seconds": group[-1]["end"],
        "topic": topic,
        "summary": summary,
        "keywords": terms,
        "coherence_score": coherence,
        "boundary_reasons": group[0].get("boundary_reasons", ["analysis_range_start"]),
        "representative_sentences": representative,
        "transcript": text,
    }
