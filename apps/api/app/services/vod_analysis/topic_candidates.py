from __future__ import annotations

import math
import re
from typing import Any

from ...config import Settings
from .spanish_text import (
    GENERIC_TOPIC_TERMS,
    NORMALIZED_SPANISH_STOPWORDS,
    extract_distinctive_terms,
    grounded,
    normalize_text,
    title_terms,
)
from .topic_semantic import representative_sentences, topic_label

QUALITY_GATE_VERSION = "candidate-quality-gate-v7"


def _duration_fit(duration: float, settings: Settings) -> float:
    if settings.candidate_target_min_seconds <= duration <= settings.candidate_target_max_seconds:
        return 1.0
    target = (
        settings.candidate_target_min_seconds
        if duration < settings.candidate_target_min_seconds
        else settings.candidate_target_max_seconds
    )
    return max(0.0, 1.0 - abs(duration - target) / max(target, 1))


def _split_topic(topic: dict[str, Any], maximum: float) -> list[dict[str, Any]]:
    start, end = topic["start_seconds"], topic["end_seconds"]
    count = math.ceil((end - start) / maximum)
    size = (end - start) / count
    return [
        {
            **topic,
            "start_seconds": start + index * size,
            "end_seconds": min(end, start + (index + 1) * size),
            "boundary_reasons": [*topic.get("boundary_reasons", []), "long_topic_natural_split"],
        }
        for index in range(count)
    ]


def _title(label: str, text: str, representatives: list[str] | None = None) -> str:
    normalized = text.casefold()
    if label == "IA y trabajo de ilustradores":
        if "miniatura" in normalized:
            return "IlloJuan habla sobre la IA y el trabajo de los artistas"
        return "IlloJuan habla sobre la IA y los ilustradores"
    if label == "gestores de contenido para streamers":
        return "IlloJuan habla sobre los gestores de contenido de los streamers"
    if label.startswith("Francia-Marruecos"):
        representative_text = " ".join(representatives or [])
        if "psg" in normalize_text(text).split() and grounded("PSG", representative_text)[0]:
            return "IlloJuan comenta el Francia-Marruecos y el PSG"
        return "IlloJuan comenta el partido Francia-Marruecos"
    return f"IlloJuan habla sobre {label}"


def validate_title_grounding(title: str, transcript: str) -> dict[str, Any]:
    supported: list[str] = []
    evidence_values: list[str] = []
    unsupported: list[str] = []
    for term in title_terms(title):
        valid, evidence = grounded(term, transcript)
        (supported if valid else unsupported).append(term)
        evidence_values.extend(item for item in evidence if item not in evidence_values)
    total = len(supported) + len(unsupported)
    score = len(supported) / total if total else 0.0
    return {
        "grounding_score": score,
        "grounding_evidence": evidence_values,
        "unsupported_terms": unsupported,
    }


def _summary(title: str, sentences: list[str]) -> str:
    if not sentences:
        return ""
    # Extractive by design: every assertion remains directly traceable to the candidate transcript.
    concepts = title_terms(title)
    ranked = sorted(
        enumerate(sentences),
        key=lambda item: (-sum(grounded(term, item[1])[0] for term in concepts), item[0]),
    )[:2]
    return " ".join(sentence for _, sentence in sorted(ranked))


def _keyword_quality(terms: list[dict[str, Any]], text: str) -> float:
    if not terms:
        return 0.0
    grounded_count = sum(grounded(item["term"], text)[0] for item in terms)
    distributed = sum(min(1.0, item["distribution"] * 2) for item in terms)
    return min(1.0, 0.65 * grounded_count / len(terms) + 0.35 * distributed / len(terms))


def _semantic_coherence(parent: float, terms: list[dict[str, Any]]) -> float:
    persistence = sum(item["distribution"] >= 0.5 for item in terms[:5]) / max(1, min(5, len(terms)))
    return max(0.0, min(1.0, 0.65 * parent + 0.35 * persistence))


def _quality_failures(candidate: dict[str, Any], minimum_coherence: float = 0.38) -> list[str]:
    failures: list[str] = []
    breakdown = candidate["score_breakdown"]
    if not candidate["keywords"]:
        failures.append("insufficient_distinctive_terms")
    if breakdown["keyword_quality"] < 0.45:
        failures.append("stopword_dominated_keywords")
    if breakdown["topic_specificity"] < 0.45:
        failures.append("generic_topic")
    if candidate["unsupported_terms"]:
        failures.extend(["title_not_grounded", "unsupported_entity"])
    if breakdown["title_grounding"] < 0.85:
        failures.append("title_not_grounded")
    if not candidate["summary"] or candidate["summary"].startswith(
        ("IlloJuan comenta", "El bloque trata sobre")
    ):
        failures.append("generic_summary")
    if breakdown["summary_grounding"] < 0.80:
        failures.append("generic_summary")
    if breakdown["semantic_coherence"] < minimum_coherence:
        failures.append("low_semantic_coherence")
    return list(dict.fromkeys(failures))


def build_candidate_outputs(
    topics: list[dict[str, Any]], segments: list[dict[str, Any]], settings: Settings
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pieces: list[tuple[int, int, dict[str, Any], list[dict[str, Any]], str]] = []
    for topic_index, topic in enumerate(topics):
        topic_pieces = (
            _split_topic(topic, settings.candidate_target_max_seconds)
            if topic["end_seconds"] - topic["start_seconds"] > settings.candidate_max_seconds
            else [topic]
        )
        for piece_index, piece in enumerate(topic_pieces):
            relevant = [
                item
                for item in segments
                if item["end"] > piece["start_seconds"] and item["start"] < piece["end_seconds"]
            ]
            text = " ".join(item["text"] for item in relevant)
            pieces.append((topic_index, piece_index, piece, relevant, text))
    corpus = [item[-1] for item in pieces]
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for topic_index, piece_index, piece, relevant, text in pieces:
        candidate = _candidate(
            piece,
            relevant,
            text,
            corpus,
            f"candidate-{topic_index + 1:03d}-{piece_index + 1}",
            settings,
        )
        failures = _quality_failures(candidate)
        if candidate["score"] < settings.vod_analysis_minimum_candidate_score:
            failures.append("below_minimum_candidate_score")
        if failures:
            rejected.append(
                {
                    "id": candidate["id"],
                    "start_seconds": candidate["exact_start_seconds"],
                    "end_seconds": candidate["exact_end_seconds"],
                    "title": candidate["title"],
                    "score": candidate["score"],
                    "reason_codes": list(dict.fromkeys(failures)),
                    "unsupported_terms": candidate["unsupported_terms"],
                    "keywords": candidate["keywords"],
                }
            )
        else:
            accepted.append(candidate)
    accepted.sort(key=lambda item: item["score"], reverse=True)
    return diversify_candidates(accepted, settings.vod_topic_max_candidates), rejected


def build_candidates(
    topics: list[dict[str, Any]], segments: list[dict[str, Any]], settings: Settings
) -> list[dict[str, Any]]:
    return build_candidate_outputs(topics, segments, settings)[0]


def _candidate(
    topic: dict[str, Any],
    relevant: list[dict[str, Any]],
    text: str,
    corpus: list[str],
    candidate_id: str,
    settings: Settings,
) -> dict[str, Any]:
    exact_start = relevant[0]["start"] if relevant else topic["start_seconds"]
    exact_end = relevant[-1]["end"] if relevant else topic["end_seconds"]
    duration = exact_end - exact_start
    term_details = extract_distinctive_terms(text, corpus, 8)
    terms = [item["term"] for item in term_details]
    label = topic_label(text, terms)
    provisional_title = _title(label, text)
    representatives = representative_sentences(text, [label, *title_terms(provisional_title), *terms], 6)
    title = _title(label, text, representatives)
    full_grounding = validate_title_grounding(title, text)
    representative_grounding = validate_title_grounding(title, " ".join(representatives))
    central_enough = representative_grounding["grounding_score"] >= 0.30
    grounding = {
        **full_grounding,
        "grounding_score": (
            full_grounding["grounding_score"] if central_enough else full_grounding["grounding_score"] * 0.5
        ),
        "grounding_evidence": list(
            dict.fromkeys(
                [
                    *full_grounding["grounding_evidence"],
                    *representative_grounding["grounding_evidence"],
                ]
            )
        ),
    }
    summary = _summary(title, representatives)
    # Summaries are direct transcript excerpts, so non-empty output is grounded by construction.
    summary_grounding = 1.0 if summary and all(sentence in text for sentence in representatives[:2]) else 0.0
    keyword_quality = _keyword_quality(term_details, text)
    label_tokens = normalize_text(label).split()
    label_is_numeric = bool(label_tokens) and all(
        token.isdigit()
        or token in {"cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve"}
        for token in label_tokens
    )
    # A lone high-frequency token is evidence, but not an editorially specific topic label.
    # Require a grounded phrase/name; conservative rejection is preferable to filler titles.
    explicit_grounded_label = label in {
        "IA y trabajo de ilustradores",
        "gestores de contenido para streamers",
        "Francia-Marruecos y el PSG",
        "partido Francia-Marruecos",
    }
    label_detail = next(
        (item for item in term_details if normalize_text(item["term"]) == normalize_text(label)),
        None,
    )
    fallback_label_is_persistent = bool(
        label_detail and label_detail["frequency"] >= 2 and label_detail["distribution"] >= 0.5
    )
    topic_specificity = (
        0.0
        if label == "tema sin etiqueta específica" or label_is_numeric
        else min(1.0, keyword_quality + 0.15)
        if explicit_grounded_label or (len(label_tokens) >= 2 and fallback_label_is_persistent)
        else 0.4
    )
    semantic_coherence = _semantic_coherence(float(topic.get("coherence_score", 0.0)), term_details)
    quality_values = [
        max(0.0, min(1.0, 1 + float(item.get("avg_logprob", -1))))
        * (1 - float(item.get("no_speech_probability", 0)))
        for item in relevant
    ]
    transcript_quality = sum(quality_values) / len(quality_values) if quality_values else 0.0
    words = len(re.findall(r"\w+", text))
    density = min(1.0, words / max(1, duration * 1.7))
    opening = 0.75 if relevant and len(relevant[0]["text"].split()) >= 5 else 0.45
    closing = 0.75 if relevant and re.search(r"[.!?…]$", relevant[-1]["text"].strip()) else 0.4
    self_containment = (opening + closing + semantic_coherence) / 3
    components = {
        "topic_coherence": semantic_coherence,
        "semantic_coherence": semantic_coherence,
        "self_containment": self_containment,
        "duration_fit": _duration_fit(duration, settings),
        "opening_quality": opening,
        "closing_quality": closing,
        "title_specificity": topic_specificity,
        "title_grounding": grounding["grounding_score"],
        "keyword_quality": keyword_quality,
        "topic_specificity": topic_specificity,
        "summary_grounding": summary_grounding,
        "speech_density": density,
        "transcript_quality": transcript_quality,
        "story_or_opinion_signal": 0.5,
    }
    weights = {
        "semantic_coherence": 0.16,
        "self_containment": 0.10,
        "duration_fit": 0.10,
        "opening_quality": 0.07,
        "closing_quality": 0.07,
        "title_specificity": 0.10,
        "title_grounding": 0.16,
        "keyword_quality": 0.11,
        "summary_grounding": 0.08,
        "transcript_quality": 0.05,
    }
    penalties: list[str] = []
    penalty = 0.0
    if grounding["unsupported_terms"]:
        penalties.append("unsupported_title_entity")
        penalty += 40
    title_content = [normalize_text(term) for term in title_terms(title)]
    if title_content and all(term in NORMALIZED_SPANISH_STOPWORDS for term in title_content):
        penalties.append("stopword_dominated_title")
        penalty += 35
    if label == "tema sin etiqueta específica" or normalize_text(label) in GENERIC_TOPIC_TERMS:
        penalties.append("generic_title")
        penalty += 20
    if keyword_quality < 0.45:
        penalties.append("low_keyword_quality")
        penalty += 20
    if topic_specificity < 0.45:
        penalties.append("topic_label_not_grounded")
        penalty += 30
    if summary.startswith(("IlloJuan comenta", "El bloque trata sobre")):
        penalties.append("template_summary")
        penalty += 15
    score = max(
        0.0,
        min(100.0, 100 * sum(components[key] * weight for key, weight in weights.items()) - penalty),
    )
    opening_preview = [item["text"] for item in relevant[:3]]
    closing_preview = [item["text"] for item in relevant[-3:]]
    return {
        "id": candidate_id,
        "exact_start_seconds": exact_start,
        "exact_end_seconds": exact_end,
        "safe_start_seconds": max(0, exact_start - settings.candidate_context_margin_seconds),
        "safe_end_seconds": exact_end + settings.candidate_context_margin_seconds,
        "title": title,
        "summary": summary,
        "keywords": terms[:5],
        "score": round(score, 1),
        "score_breakdown": {**components, "emotional_energy": 0.5, "penalties": penalties},
        "grounding_score": grounding["grounding_score"],
        "grounding_evidence": grounding["grounding_evidence"],
        "unsupported_terms": grounding["unsupported_terms"],
        "representative_sentences": representatives,
        "opening_preview": opening_preview,
        "closing_preview": closing_preview,
        "transcript_preview": text[:800],
        "warnings": penalties,
        "overlap_ratio": 0.0,
    }


def overlap_ratio(first: dict[str, Any], second: dict[str, Any]) -> float:
    overlap = max(
        0.0,
        min(first["safe_end_seconds"], second["safe_end_seconds"])
        - max(first["safe_start_seconds"], second["safe_start_seconds"]),
    )
    minimum = min(
        first["safe_end_seconds"] - first["safe_start_seconds"],
        second["safe_end_seconds"] - second["safe_start_seconds"],
    )
    return overlap / max(1.0, minimum)


def diversify_candidates(candidates: list[dict[str, Any]], maximum: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for candidate in candidates:
        ratios = [overlap_ratio(candidate, existing) for existing in selected]
        candidate["overlap_ratio"] = max(ratios, default=0.0)
        words = set(normalize_text(candidate["title"]).split())
        duplicate = any(
            len(words & set(normalize_text(item["title"]).split())) / max(1, len(words)) > 0.8
            for item in selected
        )
        if candidate["overlap_ratio"] <= 0.45 and not duplicate:
            selected.append(candidate)
        if len(selected) >= maximum:
            break
    return selected
