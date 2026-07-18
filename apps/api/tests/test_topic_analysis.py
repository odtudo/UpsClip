import sys
import types
from pathlib import Path

from apps.api.app.services.vod_analysis.cache import SourceIdentity
from apps.api.app.services.vod_analysis.spanish_text import (
    SPANISH_STOPWORDS,
    extract_distinctive_terms,
    grounded,
    normalize_text,
)
from apps.api.app.services.vod_analysis.topic_audio import chunk_ranges
from apps.api.app.services.vod_analysis.topic_cache import topic_cache_keys
from apps.api.app.services.vod_analysis.topic_candidates import (
    build_candidate_outputs,
    build_candidates,
    diversify_candidates,
    validate_title_grounding,
)
from apps.api.app.services.vod_analysis.topic_semantic import (
    LocalEmbeddingAnalyzer,
    detect_topic_blocks,
    representative_sentences,
    semantic_windows,
)
from apps.api.app.services.vod_analysis.topic_transcription import clean_transcript, merge_chunk_transcripts


def segment(start: float, end: float, text: str, logprob: float = -0.2) -> dict:
    return {
        "start": start,
        "end": end,
        "text": text,
        "words": [],
        "avg_logprob": logprob,
        "no_speech_probability": 0.02,
    }


def test_chunking_has_bounded_overlap_and_partial_tail() -> None:
    assert chunk_ranges(4000, 1800, 15) == [(0, 1800), (1785, 3585), (3570, 4000)]


def test_overlap_merge_preserves_absolute_timestamps_and_removes_duplicate() -> None:
    merged = merge_chunk_transcripts(
        [
            [segment(1780, 1792, "El tema de GTA VI")],
            [segment(1785, 1792, "El tema de GTA VI"), segment(1792, 1800, "sale más tarde")],
        ],
        15,
    )
    assert [item["text"] for item in merged] == ["El tema de GTA VI", "sale más tarde"]
    assert merged[0]["start"] >= 1780


def test_cleaning_is_non_destructive_and_removes_repeated_hallucination() -> None:
    values = [segment(index * 5, index * 5 + 4, "Suscríbete al canal") for index in range(4)]
    clean, warnings = clean_transcript(values)
    assert len(clean) == 2
    assert clean[0]["raw_text"] == "Suscríbete al canal"
    assert "repeated_whisper_hallucination_removed" in warnings


def test_semantic_windows_topics_and_candidates(test_settings) -> None:
    settings = test_settings.model_copy(
        update={
            "semantic_window_target_seconds": 60,
            "topic_min_seconds": 120,
            "candidate_min_seconds": 100,
            "vod_analysis_minimum_candidate_score": 30,
        }
    )
    segments = []
    for index in range(12):
        text = (
            "Bueno chat, GTA VI Rockstar precio lanzamiento historia opinión."
            if index < 6
            else "Cambiando de tema, aeropuerto viaje maleta anécdota historia increíble."
        )
        segments.append(segment(index * 60, index * 60 + 55, text))
    windows = semantic_windows(segments, settings)
    analyzer = LocalEmbeddingAnalyzer("missing-local-model")
    for item, embedding in zip(windows, analyzer.encode([item["text"] for item in windows]), strict=True):
        item["embedding"] = embedding
        item.pop("segments", None)
    topics = detect_topic_blocks(windows, settings)
    candidates = build_candidates(topics, segments, settings)
    assert len(topics) >= 2
    assert candidates
    assert all(item["safe_start_seconds"] <= item["exact_start_seconds"] for item in candidates)
    assert any("aeropuerto" in item["title"].casefold() for item in candidates)


def test_diversity_rejects_high_overlap() -> None:
    base = {
        "safe_start_seconds": 0,
        "safe_end_seconds": 600,
        "title": "IlloJuan habla sobre GTA VI",
        "score": 90,
    }
    duplicate = {**base, "safe_start_seconds": 20, "safe_end_seconds": 620, "score": 80}
    distinct = {
        **base,
        "safe_start_seconds": 900,
        "safe_end_seconds": 1500,
        "title": "La anécdota del aeropuerto",
        "score": 75,
    }
    assert diversify_candidates([base, duplicate, distinct], 10) == [base, distinct]


def test_staged_cache_only_invalidates_downstream(test_settings) -> None:
    identity = SourceIdentity("twitch", "123")
    first = topic_cache_keys(identity, "illojuan", test_settings)
    scoring = topic_cache_keys(
        identity, "illojuan", test_settings.model_copy(update={"vod_analysis_minimum_candidate_score": 70})
    )
    whisper = topic_cache_keys(
        identity, "illojuan", test_settings.model_copy(update={"whisper_analysis_model": "small"})
    )
    assert first["transcription"] == scoring["transcription"]
    assert first["candidates"] != scoring["candidates"]
    assert first["transcription"] != whisper["transcription"]


def test_topic_pipeline_does_not_import_visual_authority() -> None:
    source = (Path(__file__).parents[1] / "app/services/vod_analysis/analyzer.py").read_text(encoding="utf-8")
    topic_body = source.split("def _process_real", 1)[1]
    assert "layout_timeline" not in topic_body
    assert "phase_timeline" not in topic_body
    assert "detect_faces" not in topic_body


def test_colloquial_spanish_stopwords_and_fillers_are_centralized() -> None:
    for value in ("sabes", "vale", "está", "verdad", "entonces", "aquí", "mira"):
        assert normalize_text(value) in {normalize_text(item) for item in SPANISH_STOPWORDS}
    terms = extract_distinctive_terms(
        "Bueno, sabes, vale, entonces aquí mira, la inteligencia artificial "
        "sustituye ilustradores y artistas.",
        ["La inteligencia artificial sustituye ilustradores y artistas."],
    )
    assert not {"sabes", "vale", "esta", "verdad", "entonces", "aqui", "mira"} & {
        normalize_text(item["term"]) for item in terms
    }


def test_distinctive_keywords_prefer_supported_subject_matter() -> None:
    text = (
        "Las miniaturas las hacen ilustradores y artistas. Prefiero contratar un equipo de artistas "
        "antes que usar inteligencia artificial para sustituir trabajos. Ruey y Fran hacen miniaturas."
    )
    terms = [item["term"] for item in extract_distinctive_terms(text, [text, "gestores de contenido"])]
    assert any(
        value in " ".join(terms)
        for value in ("miniatura", "artista", "inteligencia artificial", "ruey", "fran")
    )


def test_bad_filler_titles_and_unsupported_gta_are_not_grounded() -> None:
    transcript = "Hablamos de miniaturas, ilustradores y de contratar artistas como Ruey y Fran."
    assert validate_title_grounding("IlloJuan habla sobre GTA VI", transcript)["unsupported_terms"]
    assert validate_title_grounding("IlloJuan habla sobre sabes y verdad", transcript)["grounding_score"] == 0
    assert validate_title_grounding("IlloJuan habla sobre vale y está", transcript)["grounding_score"] == 0


def test_supported_named_entities_are_accepted() -> None:
    result = validate_title_grounding(
        "IlloJuan comenta el partido Francia-Marruecos",
        "Ahora vamos a comentar el partido entre Francia y Marruecos.",
    )
    assert result["grounding_score"] == 1
    assert not result["unsupported_terms"]


def test_literal_and_conservative_lemma_grounding() -> None:
    assert grounded("Ruey", "Ruey y Fran hacen las miniaturas.")[0]
    assert grounded("trabajo de ilustradores", "Los ilustradores hacen esos trabajos.")[0]
    assert not grounded("GTA VI", "Habla de videojuegos y de una ilustración.")[0]


def test_quality_gate_rejects_stopword_dominated_candidate(test_settings) -> None:
    settings = test_settings.model_copy(update={"vod_analysis_minimum_candidate_score": 0})
    segments = [segment(0, 360, "Bueno, sabes, vale, está, entonces, aquí, mira, la verdad.")]
    topic = {
        "start_seconds": 0,
        "end_seconds": 360,
        "topic": "sabes y verdad",
        "summary": "",
        "keywords": ["sabes", "verdad"],
        "coherence_score": 0.9,
        "boundary_reasons": [],
        "transcript": segments[0]["text"],
    }
    accepted, rejected = build_candidate_outputs([topic], segments, settings)
    assert not accepted
    assert rejected
    assert "insufficient_distinctive_terms" in rejected[0]["reason_codes"]


def test_rejected_filler_candidate_score_is_not_inflated(test_settings) -> None:
    settings = test_settings.model_copy(update={"vod_analysis_minimum_candidate_score": 55})
    segments = [segment(0, 360, "Vale, sabes, está, verdad, entonces, aquí, mira.")]
    topic = {
        "start_seconds": 0,
        "end_seconds": 360,
        "topic": "vale y está",
        "summary": "",
        "keywords": [],
        "coherence_score": 0.95,
        "boundary_reasons": [],
        "transcript": segments[0]["text"],
    }
    accepted, rejected = build_candidate_outputs([topic], segments, settings)
    assert not accepted
    assert rejected[0]["score"] < 55


def test_grounded_candidate_has_specific_summary_and_representatives(test_settings) -> None:
    text = (
        "Las miniaturas del canal las hacen ilustradores profesionales. "
        "Yo prefiero contratar artistas antes que usar inteligencia artificial para sustituir su trabajo. "
        "Ruey y Fran forman el equipo de artistas y preparan cada ilustración. "
    ) * 12
    segments = [segment(index * 60, index * 60 + 55, text) for index in range(8)]
    topic = {
        "start_seconds": 0,
        "end_seconds": 475,
        "topic": "IA y trabajo de ilustradores",
        "summary": "",
        "keywords": ["miniaturas", "ilustradores"],
        "coherence_score": 0.85,
        "boundary_reasons": [],
        "transcript": text,
    }
    settings = test_settings.model_copy(update={"vod_analysis_minimum_candidate_score": 30})
    accepted, rejected = build_candidate_outputs([topic], segments, settings)
    assert not rejected
    assert accepted
    candidate = accepted[0]
    assert "artistas" in candidate["title"].casefold()
    assert candidate["grounding_score"] >= 0.85
    assert candidate["representative_sentences"]
    assert "miniaturas" in candidate["summary"].casefold() or "artistas" in candidate["summary"].casefold()
    assert not candidate["summary"].startswith("El bloque trata sobre")


def test_representative_sentences_exclude_filler_only_lines() -> None:
    text = (
        "Bueno, sabes, vale, la verdad. "
        "Los ilustradores profesionales preparan las miniaturas del canal con un estilo propio. "
        "Ruey y Fran forman el equipo de artistas contratado para hacer esas imágenes."
    )
    values = representative_sentences(text, ["ilustradores", "equipo de artistas"], 3)
    assert values
    assert all("Bueno, sabes" not in item for item in values)


def test_fixture_and_real_cache_are_incompatible_and_title_version_is_present(test_settings) -> None:
    identity = SourceIdentity("twitch", "2814270995")
    real = topic_cache_keys(
        identity,
        "illojuan",
        test_settings,
        source_url="https://twitch.tv/videos/2814270995",
        transcript_hash="abc",
    )
    fixture = topic_cache_keys(
        identity,
        "illojuan",
        test_settings.model_copy(update={"vod_analysis_fixture_mode": True}),
        source_url="https://twitch.tv/videos/2814270995",
        transcript_hash="abc",
    )
    different_source = topic_cache_keys(
        identity,
        "illojuan",
        test_settings,
        source_url="https://youtube.com/watch?v=2814270995",
        transcript_hash="abc",
    )
    assert real["candidates"] != fixture["candidates"]
    assert real["candidates"] != different_source["candidates"]
    assert (
        real["segmentation"]
        != topic_cache_keys(identity, "illojuan", test_settings, source_url="x", transcript_hash="def")[
            "segmentation"
        ]
    )


def test_embedding_backend_reports_effective_model(monkeypatch) -> None:
    class FakeEmbedding:
        def __init__(self, **_kwargs):
            pass

        def embed(self, texts):
            return ([1.0, 0.0, 0.0] for _ in texts)

    monkeypatch.setitem(sys.modules, "fastembed", types.SimpleNamespace(TextEmbedding=FakeEmbedding))
    analyzer = LocalEmbeddingAnalyzer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    analyzer.encode(["miniaturas e ilustradores"])
    assert analyzer.details()["effective_backend"].endswith("MiniLM-L12-v2")
    assert analyzer.details()["model_loaded"] is True
    assert analyzer.details()["fallback_used"] is False


def test_embedding_fallback_is_reported_truthfully(monkeypatch) -> None:
    class BrokenEmbedding:
        def __init__(self, **_kwargs):
            raise ValueError("model unavailable")

    monkeypatch.setitem(sys.modules, "fastembed", types.SimpleNamespace(TextEmbedding=BrokenEmbedding))
    analyzer = LocalEmbeddingAnalyzer("missing-model")
    analyzer.encode(["texto"])
    details = analyzer.details()
    assert details["effective_backend"] == "multilingual-hash-fallback-v2"
    assert details["fallback_used"] is True
    assert "model unavailable" in details["fallback_reason"]
