"""
Analytics — Phase 4.

Text cleaning, normalisation, and category/severity assignment.
All logic is rule-based. No ML or AI in this layer.
"""

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_ENTITY_RE = re.compile(r"&(?:#\d+|#x[\da-fA-F]+|[a-zA-Z]+);")
_WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")   # collapse horizontal whitespace only
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")        # collapse 3+ newlines → 2
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")  # remove control chars

# Common HTML entities not covered by html.unescape in edge cases
_ENTITY_MAP = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#39;": "'",
    "&apos;": "'",
    "&nbsp;": " ",
    "&mdash;": "—",
    "&ndash;": "–",
    "&hellip;": "…",
}


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

def _unescape_entities(text: str) -> str:
    """Replace common HTML entities with their unicode equivalents."""
    import html
    text = html.unescape(text)
    for entity, char in _ENTITY_MAP.items():
        text = text.replace(entity, char)
    return text


def clean_text(text: str) -> str:
    """
    Full cleaning pipeline:
      1. Strip HTML tags
      2. Unescape HTML entities
      3. Remove C0 control characters (preserve \n, \t)
      4. Normalise unicode to NFC form
      5. Collapse horizontal whitespace
      6. Strip leading/trailing whitespace
      7. Guarantee valid UTF-8 (replace any residual bad bytes)

    Returns an empty string if text is None or empty.
    """
    if not text:
        return ""

    # 1. Strip HTML tags
    text = _HTML_TAG_RE.sub(" ", text)

    # 2. Unescape entities
    text = _unescape_entities(text)

    # 3. Remove control characters (keep \n for paragraph structure)
    text = _CONTROL_CHAR_RE.sub("", text)

    # 4. Unicode NFC normalisation (e.g. accented chars)
    text = unicodedata.normalize("NFC", text)

    # 5. Collapse horizontal whitespace runs to single space
    text = _WHITESPACE_RE.sub(" ", text)

    # 6. Collapse multiple blank lines
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)

    # 7. Strip
    text = text.strip()

    # 8. Safe UTF-8 round-trip (catches any stray surrogate bytes)
    text = text.encode("utf-8", errors="replace").decode("utf-8")

    return text


# ---------------------------------------------------------------------------
# Dollar-amount extractor (used by severity)
# ---------------------------------------------------------------------------

_DOLLAR_AMOUNT_RE = re.compile(
    r"\$\s*(?P<amount>[\d,]+(?:\.\d+)?)\s*(?P<unit>billion|million|m\b|k\b|thousand)?",
    re.IGNORECASE,
)

_UNIT_MULTIPLIER = {
    "billion": 1_000_000_000,
    "million": 1_000_000,
    "m": 1_000_000,
    "k": 1_000,
    "thousand": 1_000,
}


def extract_max_dollar_amount(text: str) -> float:
    """
    Return the largest dollar amount found in text, normalised to USD.
    Returns 0.0 if no amount found.

    Examples:
        "$5 million"   → 5_000_000.0
        "$100M"        → 100_000_000.0
        "$500k"        → 500_000.0
        "$3.98 million"→ 3_980_000.0
    """
    text_lower = text.lower()
    max_amount = 0.0
    for m in _DOLLAR_AMOUNT_RE.finditer(text_lower):
        raw = m.group("amount").replace(",", "")
        unit = (m.group("unit") or "").lower().rstrip(".")
        try:
            value = float(raw) * _UNIT_MULTIPLIER.get(unit, 1)
            if value > max_amount:
                max_amount = value
        except ValueError:
            continue
    return max_amount


# ---------------------------------------------------------------------------
# Normalisation entry point
# ---------------------------------------------------------------------------

def normalize_report(report) -> None:
    """
    Full Phase 4 normalization pipeline for a single HackReport:
      1. Clean title and description
      2. Assign category (keyword rules, first match wins)
      3. Assign severity (dollar-amount aware + keyword rules)
      4. Sync scraped tags from raw_data into the Tag M2M relation
      5. Set is_processed = True
      6. Save (update_fields only — no unnecessary full-row write)

    Caller does NOT need to call .save() separately.
    """
    from reports.services.category_service import assign_category, assign_severity_smart  # noqa: PLC0415
    from analytics.tag_sync import sync_tags  # noqa: PLC0415

    report.title = clean_text(report.title)
    report.description = clean_text(report.description)

    combined = f"{report.title} {report.description}"

    # Only assign if not already set (preserves manual overrides)
    if report.category is None:
        report.category = assign_category(combined)

    report.severity = assign_severity_smart(combined)
    report.is_processed = True

    report.save(update_fields=["title", "description", "category", "severity", "is_processed"])

    # Sync tags from raw_data after save (needs PK to exist)
    sync_tags(report)

    logger.info(
        "Normalised report id=%s title=%r severity=%s category=%s",
        report.pk,
        report.title[:60],
        report.severity,
        report.category,
    )
