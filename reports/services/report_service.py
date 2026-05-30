"""
Report service.

Handles creation and update of HackReport records.
Business logic only — no HTTP, no scraping.
"""

import logging
from typing import Any

from reports.services.dedup_service import compute_hash

logger = logging.getLogger(__name__)


def create_report(
    *,
    title: str,
    description: str,
    source_url: str,
    source: str,
    raw_data: dict[str, Any] | None = None,
    published_at=None,
) -> "reports.models.HackReport":  # noqa: F821
    """
    Create and return a new HackReport.

    The caller is responsible for calling is_duplicate() first.
    Raises django.db.IntegrityError if the hash already exists (DB-level guard).
    """
    from reports.models import HackReport  # noqa: PLC0415

    report = HackReport.objects.create(
        title=title,
        description=description,
        source_url=source_url,
        source=source,
        hash=compute_hash(source_url),
        is_processed=False,
        raw_data=raw_data or {},
        published_at=published_at,
    )
    logger.info("Created HackReport id=%s source=%s", report.pk, source)
    return report
