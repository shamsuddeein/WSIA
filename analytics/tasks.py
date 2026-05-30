"""
Celery tasks — Phase 5 pipeline automation.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_pipeline(self):
    """
    Full pipeline task:
      1. Scrape rekt.news
      2. Deduplicate
      3. Store raw records (is_processed=False)
      4. Normalise + assign category/severity (is_processed=True)

    Phase 5 — not active until Celery + Redis are running.
    """
    from reports.services.dedup_service import is_duplicate  # noqa: PLC0415
    from reports.services.report_service import create_report  # noqa: PLC0415
    from analytics.cleaner import normalize_report  # noqa: PLC0415

    try:
        # Import here to avoid importing scraper at module level
        from reports.scraper import scrape_rekt  # noqa: PLC0415

        articles = scrape_rekt()
    except Exception as exc:
        logger.exception("Scraper failed: %s", exc)
        raise self.retry(exc=exc)

    new_count = 0
    skipped_count = 0

    for article in articles:
        if is_duplicate(article["source_url"]):
            skipped_count += 1
            continue
        try:
            report = create_report(**article)
            normalize_report(report)
            new_count += 1
        except Exception:
            logger.exception("Failed to process article: %s", article.get("source_url"))

    logger.info(
        "Pipeline complete — new=%d skipped=%d",
        new_count,
        skipped_count,
    )
    return {"new": new_count, "skipped": skipped_count}
