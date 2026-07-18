from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from typing import Any

SPANISH_FILLER_PHRASES = {
    "a ver",
    "en plan",
    "o sea",
    "yo que sé",
    "la verdad",
    "es verdad",
    "no sé",
    "qué sé yo",
    "por cierto",
}

SPANISH_STOPWORDS = {
    "a",
    "acá",
    "ah",
    "ahí",
    "ahora",
    "al",
    "algo",
    "alguien",
    "algún",
    "alguna",
    "algunas",
    "alguno",
    "algunos",
    "ante",
    "antes",
    "aquí",
    "así",
    "aun",
    "aunque",
    "bien",
    "bueno",
    "cada",
    "casi",
    "claro",
    "como",
    "cómo",
    "con",
    "contra",
    "cosa",
    "cosas",
    "cual",
    "cuando",
    "de",
    "del",
    "desde",
    "donde",
    "dos",
    "durante",
    "e",
    "eh",
    "el",
    "él",
    "ella",
    "ellas",
    "ellos",
    "en",
    "entonces",
    "entre",
    "era",
    "erais",
    "eran",
    "eras",
    "eres",
    "es",
    "esa",
    "esas",
    "ese",
    "eso",
    "esos",
    "esta",
    "está",
    "estaba",
    "estaban",
    "estado",
    "estamos",
    "están",
    "estar",
    "estas",
    "este",
    "esto",
    "estos",
    "estoy",
    "fue",
    "fuera",
    "fueron",
    "hacer",
    "hace",
    "haces",
    "hacia",
    "hay",
    "incluso",
    "ir",
    "la",
    "las",
    "le",
    "les",
    "literal",
    "literalmente",
    "lo",
    "los",
    "luego",
    "más",
    "me",
    "menos",
    "mi",
    "mientras",
    "mira",
    "mismo",
    "mucho",
    "muy",
    "nada",
    "ni",
    "ningún",
    "no",
    "nos",
    "nosotros",
    "nuestra",
    "nuestro",
    "nunca",
    "o",
    "otra",
    "otro",
    "para",
    "pero",
    "poco",
    "por",
    "porque",
    "pues",
    "que",
    "qué",
    "realmente",
    "sabe",
    "sabéis",
    "sabemos",
    "saben",
    "sabes",
    "ser",
    "si",
    "sí",
    "siempre",
    "sin",
    "sobre",
    "solo",
    "somos",
    "son",
    "su",
    "sus",
    "tal",
    "también",
    "te",
    "tengo",
    "tiene",
    "tienen",
    "tipo",
    "toda",
    "todo",
    "todos",
    "tres",
    "tú",
    "un",
    "una",
    "uno",
    "unos",
    "usted",
    "va",
    "vale",
    "vamos",
    "verdad",
    "y",
    "ya",
    "yo",
}

GENERIC_TOPIC_TERMS = {
    "años",
    "chat",
    "directo",
    "final",
    "gente",
    "hombre",
    "juego",
    "momento",
    "mundo",
    "parte",
    "persona",
    "personas",
    "tema",
    "tiempo",
    "tío",
    "video",
    "vídeo",
    "vez",
}


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(
        re.findall(r"[a-z0-9]+", "".join(char for char in value if not unicodedata.combining(char)))
    )


NORMALIZED_SPANISH_STOPWORDS = {normalize_text(value) for value in SPANISH_STOPWORDS}
NORMALIZED_GENERIC_TOPIC_TERMS = {normalize_text(value) for value in GENERIC_TOPIC_TERMS}


def basic_lemma(token: str) -> str:
    normalized = normalize_text(token)
    irregular = {
        "artistas": "artista",
        "ilustradores": "ilustrador",
        "miniaturas": "miniatura",
        "gestores": "gestor",
        "trabajos": "trabajo",
    }
    if normalized in irregular:
        return irregular[normalized]
    for suffix in ("amientos", "imiento", "aciones", "adores", "adoras", "mente"):
        if normalized.endswith(suffix) and len(normalized) > len(suffix) + 3:
            return normalized[: -len(suffix)]
    if normalized.endswith("es") and len(normalized) > 5:
        return normalized[:-2]
    if normalized.endswith("s") and len(normalized) > 4:
        return normalized[:-1]
    return normalized


def is_content_token(token: str) -> bool:
    normalized = normalize_text(token)
    return (
        len(normalized) >= 4
        and normalized not in NORMALIZED_SPANISH_STOPWORDS
        and normalized not in NORMALIZED_GENERIC_TOPIC_TERMS
    )


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+", text)


def candidate_terms(text: str) -> Counter[str]:
    raw = _tokens(text)
    lowered = [token.casefold() for token in raw]
    result: Counter[str] = Counter()
    for token in lowered:
        if is_content_token(token):
            result[basic_lemma(token)] += 1
    for size in (2, 3):
        for index in range(len(lowered) - size + 1):
            phrase_tokens = lowered[index : index + size]
            if not is_content_token(phrase_tokens[0]) or not is_content_token(phrase_tokens[-1]):
                continue
            if sum(is_content_token(token) for token in phrase_tokens) < 2:
                continue
            phrase = " ".join(phrase_tokens)
            if phrase not in SPANISH_FILLER_PHRASES:
                result[phrase] += 1
    return result


def extract_distinctive_terms(text: str, corpus: list[str], maximum: int = 8) -> list[dict[str, Any]]:
    counts = candidate_terms(text)
    if not counts:
        return []
    documents = [set(candidate_terms(item)) for item in corpus]
    normalized = normalize_text(text)
    quarters = [
        normalized[index * len(normalized) // 4 : (index + 1) * len(normalized) // 4] for index in range(4)
    ]
    scored: list[dict[str, Any]] = []
    for term, frequency in counts.items():
        document_frequency = sum(term in document for document in documents)
        idf = math.log((1 + len(documents)) / (1 + document_frequency)) + 1
        distribution = sum(normalize_text(term) in quarter for quarter in quarters) / 4
        phrase_bonus = 1.35 if " " in term else 1.0
        generic_penalty = 0.35 if term in GENERIC_TOPIC_TERMS else 1.0
        score = math.log1p(frequency) * idf * (0.65 + 0.35 * distribution) * phrase_bonus * generic_penalty
        scored.append(
            {
                "term": term,
                "score": score,
                "frequency": frequency,
                "document_frequency": document_frequency,
                "distribution": distribution,
            }
        )
    scored.sort(key=lambda item: (-item["score"], -item["frequency"], item["term"]))
    selected: list[dict[str, Any]] = []
    for item in scored:
        term = item["term"]
        if any(term in previous["term"] or previous["term"] in term for previous in selected):
            continue
        selected.append(item)
        if len(selected) >= maximum:
            break
    return selected


def filler_ratio(text: str) -> float:
    tokens = _tokens(text)
    if not tokens:
        return 1.0
    return sum(normalize_text(token) in SPANISH_STOPWORDS for token in tokens) / len(tokens)


def grounded(term: str, transcript: str) -> tuple[bool, list[str]]:
    normalized_term = normalize_text(term)
    normalized_transcript = normalize_text(transcript)
    if normalized_term == "ia" and "inteligencia artificial" in normalized_transcript:
        return True, ["inteligencia artificial"]
    if normalized_term and f" {normalized_term} " in f" {normalized_transcript} ":
        return True, [term]
    term_lemmas = [basic_lemma(token) for token in normalized_term.split() if is_content_token(token)]
    transcript_lemmas = {basic_lemma(token) for token in normalized_transcript.split()}
    if term_lemmas and all(lemma in transcript_lemmas for lemma in term_lemmas):
        return True, term_lemmas
    return False, []


def title_terms(title: str) -> list[str]:
    stripped = re.sub(r"^IlloJuan\s+(habla|comenta|explica)\s+(sobre\s+)?", "", title, flags=re.I)
    return [
        token for token in _tokens(stripped) if is_content_token(token) or token.isupper() or token.isdigit()
    ]
