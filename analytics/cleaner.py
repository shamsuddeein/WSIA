"""
Analytics — Phase 4.

Text cleaning, normalisation, and category/severity assignment.
All logic is rule-based. No ML or AI in this layer.
"""

import logging
import re

logger = logging.getLogger(__name__)

# ── HTML tag stripper ────────────────────────────────────────────────────────
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    """
    Strip HTML tags, collapse whitespace, and ensure valid UTF-8.

    Returns an empty string if text is None or empty.
    """
    if not text:
        return ""
    # Remove HTML tags
    text = _HTML_TAG_RE.sub(" ", text)
    # Collapse whitespace
    text = _WHITESPACE_RE.sub(" ", text).strip()
    # Ensure clean UTF-8 — replace undecodable bytes
    text = text.encode("utf-8", errors="replace").decode("utf-8")
    return text


def normalize_report(report) -> None:
    """
    Clean title and description in-place and set is_processed=True.

    Also assigns category and severity via rule-based services.
    Saves the report. Caller does not need to call .save() separately.
    """
    from reports.services.category_service import assign_category, assign_severity  # noqa: PLC0415

    report.title = clean_text(report.title)
    report.description = clean_text(report.description)

    combined = f"{report.title} {report.description}"

    if report.category is None:
        report.category = assign_category(combined)

    report.severity = assign_severity(combined)
    report.is_processed = True

    report.save(update_fields=["title", "description", "category", "severity", "is_processed"])
    logger.info("Normalised report id=%s", report.pk)
