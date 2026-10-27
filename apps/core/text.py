"""Text helpers: name normalisation, trigram similarity and contact masking."""

from __future__ import annotations

import re
import unicodedata

ABBREVIATIONS = [
    (r"\bn ?& ?m\b", "nurses and midwifery"),
    (r"\bnmtc\b", "nurses and midwifery training college"),
    (r"\buniv\b", "university"),
    (r"\buni\b", "university"),
    (r"\btech\b", "technical"),
    (r"\bcoll\b", "college"),
    (r"\bcoe\b", "college of education"),
]


def strip_accents(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c)
    )


def normalise_name(value: str | None) -> str:
    """Normalise institution/place names for matching (DATA_SOURCES_PROMPT §6)."""
    if not value:
        return ""
    text = strip_accents(value).lower()
    for pattern, repl in ABBREVIATIONS[:1]:
        text = re.sub(pattern, repl, text)
    text = text.replace("&", " and ")
    text = re.sub(r"[^\w\s]", " ", text)
    for pattern, repl in ABBREVIATIONS[1:]:
        text = re.sub(pattern, repl, text)
    return re.sub(r"\s+", " ", text).strip()


def _trigrams(value: str) -> set[str]:
    """Trigrams the way PostgreSQL pg_trgm builds them: per word, padded with spaces."""
    grams: set[str] = set()
    for word in re.findall(r"[a-z0-9]+", value.lower()):
        padded = f"  {word} "
        for i in range(len(padded) - 2):
            grams.add(padded[i : i + 3])
    return grams


def trigram_similarity(a: str | None, b: str | None) -> float:
    ga, gb = _trigrams(a or ""), _trigrams(b or "")
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


# ---------------------------------------------------------------------------
# Masking of contact details in comments (§6.7)
# ---------------------------------------------------------------------------
HIDDEN = "[hidden]"
_SEP = r"[\s\-\.]*"
PHONE_RE = re.compile(
    r"(?:(?:\+|00)\s*233" + _SEP + r"\(?0?\)?" + _SEP + r"\d" + r"(?:" + _SEP + r"\d){8}"
    r"|\b0" + _SEP + r"\d(?:" + _SEP + r"\d){8}\b)"
)
EMAIL_RE = re.compile(r"[\w.+-]+\s*(?:@|\(at\)|\[at\])\s*[\w-]+(?:\s*(?:\.|\(dot\))\s*[\w-]+)+", re.I)
URL_RE = re.compile(
    r"(?:https?://|www\.)\S+|\b[\w-]+\.(?:com|net|org|gh|io|co|me|ly|info|biz|xyz|app|link)(?:/\S*)?\b",
    re.I,
)


def mask_contacts(text: str | None) -> str:
    if not text:
        return ""
    text = EMAIL_RE.sub(HIDDEN, text)
    text = URL_RE.sub(HIDDEN, text)
    text = PHONE_RE.sub(HIDDEN, text)
    return text
