"""Conservative rule-based parsing of Russian radiology text.

The parser only exposes traceable text signals. It never diagnoses a patient
and never overrides structured fields supplied by the upstream AI service.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Pattern

from app.models.normalized import (
    Evidence,
    Modality,
    TextAssertion,
    TextSignal,
    TextSource,
)


@dataclass(frozen=True)
class _Rule:
    code: str
    display_name: str
    pattern: Pattern[str]


_NEGATION = re.compile(
    r"(?:\bне\s+(?:выяв\w*|определ\w*|обнаруж\w*|визуализ\w*)"
    r"|\bбез\s+(?:убедительных\s+)?признак\w*"
    r"|\ботсутств\w*)",
    re.IGNORECASE,
)
_UNCERTAINTY = re.compile(
    r"(?:\bвероят\w*|\bвозможн\w*|\bнельзя\s+исключить\b|\bпод\s+вопросом\b)",
    re.IGNORECASE,
)
_GLOBAL_NORMAL = re.compile(
    r"(?:"
    r"(?:патолог\w*|признак\w*\s+патолог\w*).{0,100}"
    r"не\s+(?:выяв\w*|определ\w*|обнаруж\w*)"
    r"|не\s+(?:выяв\w*|определ\w*|обнаруж\w*).{0,100}патолог\w*"
    r"|без\s+(?:убедительных\s+)?признак\w*.{0,80}патолог\w*"
    r"|патолог\w*.{0,80}отсутств\w*"
    r")",
    re.IGNORECASE,
)

_CT_RULES = (
    _Rule(
        "CT_LUNG_NODULE",
        "Очаговое образование лёгкого",
        re.compile(r"\b(?:очаг\w*|образовани\w*)\b", re.IGNORECASE),
    ),
    _Rule(
        "CT_PNEUMOTHORAX",
        "Пневмоторакс",
        re.compile(
            r"(?:\bпневмоторакс\w*\b|свободн\w*\s+газ\w*.{0,50}плевральн\w*)",
            re.IGNORECASE,
        ),
    ),
)

_MAMMOGRAPHY_RULES = (
    _Rule(
        "MMG_SUSPICIOUS_FINDING",
        "Подозрительное изменение молочной железы",
        re.compile(
            r"(?:\bподозрительн\w*\b|\bBI\s*[-–]?\s*RADS\s*[45]\b)",
            re.IGNORECASE,
        ),
    ),
    _Rule(
        "MMG_BENIGN_FINDING",
        "Доброкачественное изменение молочной железы",
        re.compile(
            r"(?:\bдоброкачественн\w*\b|\bBI\s*[-–]?\s*RADS\s*2\b)",
            re.IGNORECASE,
        ),
    ),
)


def _sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?;])\s+", text.strip())
        if sentence.strip()
    ]


def _assertion(sentence: str) -> TextAssertion:
    if _NEGATION.search(sentence):
        return TextAssertion.NEGATED
    if _UNCERTAINTY.search(sentence):
        return TextAssertion.UNCERTAIN
    return TextAssertion.PRESENT


def analyze_text(
    text: str,
    *,
    source: TextSource,
    modality: Modality,
) -> list[TextSignal]:
    """Extract conservative text signals with exact sentence evidence."""

    source_path = "aiResult.report" if source is TextSource.REPORT else "aiResult.conclusion"
    rules = {
        Modality.CT_CHEST: _CT_RULES,
        Modality.MAMMOGRAPHY: _MAMMOGRAPHY_RULES,
        Modality.UNKNOWN: (),
    }[modality]
    signals: list[TextSignal] = []

    for sentence in _sentences(text):
        evidence = [Evidence(source_path=source_path, raw_value=sentence)]

        if _GLOBAL_NORMAL.search(sentence):
            signals.append(
                TextSignal(
                    code="GLOBAL_PATHOLOGY",
                    display_name="Общее указание на отсутствие патологии",
                    assertion=TextAssertion.NEGATED,
                    source=source,
                    matched_text=sentence,
                    evidence=evidence,
                )
            )

        for rule in rules:
            if rule.pattern.search(sentence):
                signals.append(
                    TextSignal(
                        code=rule.code,
                        display_name=rule.display_name,
                        assertion=_assertion(sentence),
                        source=source,
                        matched_text=sentence,
                        evidence=evidence,
                    )
                )

    return signals

