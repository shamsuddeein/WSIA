"""
Deduplication service.

All duplicate checks must go through this module.
Never inline hash logic in scrapers or views.
"""

import hashlib
import logging

logger = logging.getLogger(__name__)


def compute_hash(url: str) -> str:
    """Return the SHA-256 hex digest of a URL string."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def is_duplicate(url: str) -> bool:
    """
    Return True if a HackReport with this URL's hash already exists.

    Importing lazily to avoid circular imports at module load time.
    """
    from reports.models import HackReport  # noqa: PLC0415

    h = compute_hash(url)
    exists = HackReport.objects.filter(hash=h).exists()
    if exists:
        logger.debug("Duplicate detected for URL: %s (hash=%s)", url, h)
    return exists
