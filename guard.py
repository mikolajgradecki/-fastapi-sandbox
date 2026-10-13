"""Prompt injection defense that does not depend on the model.

The model is also asked to report suspicious fragments, but an injection can talk it out of that.
These patterns are the backstop, and safe_text keeps flagged text out of the reply to the customer.
"""

import re

SUSPICIOUS_PATTERNS = [
    # Requests for discounts or free goods
    r"\brabat\w*",
    r"\bzni[żz]k\w*",
    r"\bobni[żz]\w*\s+cen\w*",
    r"\bgratis\w*",
    r"\bza\s+darmo\b",
    r"\bdiscount\w*",
    r"\bfor\s+free\b",
    r"\d{1,3}\s?%\s*(taniej|off)\b",
    # Instructions aimed at the AI instead of the sales team
    r"\bzignoruj\w*",
    r"\bpoprzedni\w*\s+(instrukcj|polece)\w*",
    r"\binstrukcj\w*\s+(dla|do)\s+(ai|ia|modelu|asystenta|systemu|bota)\b",
    r"\bsystem\w*\s+prompt\w*",
    r"\bjeste[śs]\s+(teraz\s+)?(ai|modelem|asystentem|botem)\b",
    r"\bignore\s+(all\s+|any\s+|the\s+)?(previous\s+|prior\s+|above\s+)?(instructions|rules|prompts?)\b",
    r"\byou\s+are\s+(now\s+)?(an?\s+)?(ai|assistant|language\s+model|chatbot)\b",
    r"\bact\s+as\b",
    r"\b(ustaw|set)\w*\s+(wszystkie\s+|all\s+)?(ceny|cen[eę]|prices?)\b",
]
_PATTERN = re.compile("|".join(f"(?:{pattern})" for pattern in SUSPICIOUS_PATTERNS), re.IGNORECASE)

MAX_FRAGMENT_LENGTH = 160
MAX_FLAGS = 10


def is_suspicious(text: str) -> bool:
    return _PATTERN.search(text) is not None


def find_suspicious(text: str) -> list[str]:
    """Sentences of the text that match a suspicious pattern."""
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [
        _shorten(sentence)
        for sentence in sentences
        if sentence.strip() and is_suspicious(sentence)
    ]


def merge_flags(*groups: list[str]) -> list[str]:
    """Joins flags from several sources without duplicates, keeping the first spelling."""
    seen = set()
    merged = []
    for group in groups:
        for flag in group:
            flag = _shorten(flag)
            key = flag.casefold()
            if flag and key not in seen:
                seen.add(key)
                merged.append(flag)
    return merged[:MAX_FLAGS]


def safe_text(value: str | None, max_length: int = 120) -> str | None:
    """Text from the e-mail that may go into the reply: one line, short, and not suspicious."""
    if not value:
        return None
    value = " ".join(value.split())[:max_length]
    if not value or is_suspicious(value):
        return None
    return value


def _shorten(text: str) -> str:
    text = " ".join(text.split())
    if len(text) > MAX_FRAGMENT_LENGTH:
        return text[: MAX_FRAGMENT_LENGTH - 1] + "…"
    return text
