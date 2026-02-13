from __future__ import annotations

import re
from dataclasses import dataclass

from tjr.storage.config_store import JobProfileSettings

try:
    import pymorphy3
except ImportError:  # pragma: no cover
    pymorphy3 = None

_WORD_RE = re.compile(r"[\w-]+", re.UNICODE)
_MORPH = pymorphy3.MorphAnalyzer() if pymorphy3 is not None else None

# Built-in anti-noise phrases to suppress non-vacancy content.
_SYSTEM_EXCLUSION_PHRASES = [
    "рекомендую кандидата",
    "рекомендую специалиста",
    "кандидат в поиске работы",
    "ищу работу",
    "открыт к предложениям",
    "open to work",
    "курс для",
    "курсы для",
    "вебинар для",
    "обучение для",
    "мастер-класс для",
]


@dataclass(slots=True)
class MatchResult:
    score: int
    active_criteria_count: int
    excluded: bool
    matched_title: bool
    matched_profile: bool
    matched_industry: bool
    matched_title_terms: list[str]
    matched_profile_terms: list[str]
    matched_industry_terms: list[str]
    matched_exclusion_terms: list[str]


def evaluate_message(text: str, profile: JobProfileSettings) -> MatchResult:
    text_lemmas = set(extract_lemmas(text))

    matched_title_terms = _matched_terms(profile.title_keywords, text_lemmas)
    matched_profile_terms = _matched_terms(profile.profile_keywords, text_lemmas)
    matched_industry_terms = _matched_terms(profile.industry_keywords, text_lemmas)
    matched_user_exclusion_terms = _matched_terms(profile.exclusion_phrases, text_lemmas)
    matched_system_exclusion_terms = _matched_terms(_SYSTEM_EXCLUSION_PHRASES, text_lemmas)
    matched_exclusion_terms = _dedupe_terms(matched_user_exclusion_terms + matched_system_exclusion_terms)

    active_title = bool(profile.title_keywords)
    active_profile = bool(profile.profile_keywords)
    active_industry = bool(profile.industry_keywords)

    matched_title = active_title and bool(matched_title_terms)
    matched_profile = active_profile and bool(matched_profile_terms)
    matched_industry = active_industry and bool(matched_industry_terms)

    score = int(matched_title) + int(matched_profile) + int(matched_industry)
    active_criteria_count = int(active_title) + int(active_profile) + int(active_industry)
    excluded = bool(matched_exclusion_terms)

    return MatchResult(
        score=score,
        active_criteria_count=active_criteria_count,
        excluded=excluded,
        matched_title=matched_title,
        matched_profile=matched_profile,
        matched_industry=matched_industry,
        matched_title_terms=matched_title_terms,
        matched_profile_terms=matched_profile_terms,
        matched_industry_terms=matched_industry_terms,
        matched_exclusion_terms=matched_exclusion_terms,
    )


def _matched_terms(terms: list[str], text_lemmas: set[str]) -> list[str]:
    matched: list[str] = []
    for term in terms:
        term_lemmas = extract_lemmas(term)
        if not term_lemmas:
            continue
        if all(lemma in text_lemmas for lemma in term_lemmas):
            matched.append(term)
    return matched


def _dedupe_terms(terms: list[str]) -> list[str]:
    unique_terms: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = term.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique_terms.append(term)
    return unique_terms


def extract_lemmas(text: str) -> list[str]:
    tokens = [token.lower() for token in _WORD_RE.findall(text)]
    if not tokens:
        return []

    lemmas: list[str] = []
    for token in tokens:
        if _MORPH is None:
            lemmas.append(token)
            continue
        parsed = _MORPH.parse(token)
        if parsed:
            lemmas.append(parsed[0].normal_form)
        else:
            lemmas.append(token)
    return lemmas
