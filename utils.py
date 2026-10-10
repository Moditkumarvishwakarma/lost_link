import re
from typing import Any, Iterable


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def get_tokens(value: Any) -> list[str]:
    text = normalize_text(value)
    if not text:
        return []
    return [token for token in text.split() if len(token) > 2]


def make_chip_text(items: Iterable[str]) -> str:
    cleaned = [item.strip() for item in items if item and str(item).strip()]
    return ", ".join(cleaned) if cleaned else "No major details noted."


def mask_contact(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "Not shared"
    if len(text) <= 4:
        return "***"
    return text[:2] + "***" + text[-2:]
