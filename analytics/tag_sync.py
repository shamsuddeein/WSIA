"""
Tag sync — Phase 4.

Reads scraped tag strings from HackReport.raw_data['tags'] and
materialises them as Tag model instances linked via the M2M relation.

This keeps the Tag table in sync without re-scraping.
"""

import logging

logger = logging.getLogger(__name__)


def sync_tags(report) -> None:
    """
    Sync report.raw_data['tags'] (list of strings) into report.tags (M2M).

    - Creates Tag records that don't exist yet (get_or_create).
    - Adds new tags; does NOT remove manually assigned tags.
    - Silently skips if raw_data has no 'tags' key.
    """
    from reports.models import Tag  # noqa: PLC0415

    raw_tags: list[str] = report.raw_data.get("tags", [])
    if not raw_tags:
        return

    added = []
    for tag_name in raw_tags:
        tag_name = tag_name.strip()
        if not tag_name:
            continue
        tag, created = Tag.objects.get_or_create(name=tag_name)
        if created:
            logger.debug("Created tag: %r", tag_name)
        report.tags.add(tag)
        added.append(tag_name)

    if added:
        logger.debug("Synced tags for report id=%s: %s", report.pk, added)
