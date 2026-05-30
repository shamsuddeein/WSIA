"""
Celery tasks — Phase 5 pipeline automation.

Tasks:
    run_pipeline          — full scrape → dedup → store → normalise cycle
    normalize_unprocessed — cleans any records that weren't normalised yet
    scrape_only           — scrape + store raw records, skip normalisation
"""

import logging

from celery import shared_task
from django.db import transaction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_run_model():
    from core.models import PipelineRun  # noqa: PLC0415
    return PipelineRun


# ---------------------------------------------------------------------------
# Main pipeline task
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=120,   # wait 2 min before retrying a scrape failure
    time_limit=3600,           # hard kill after 1 hour
    soft_time_limit=3300,      # SoftTimeLimitExceeded raised at 55 min
    name="analytics.tasks.run_pipeline",
)
def run_pipeline(self, max_pages: int = 5) -> dict:
    """
    Full pipeline:
      1. Open a PipelineRun audit record
      2. Scrape rekt.news (max_pages pages)
      3. For each article: dedup → store raw → normalise
      4. Close the PipelineRun with final counts

    Each article is processed in its own atomic transaction so that
    a single failure does not roll back the rest of the batch.

    Returns a summary dict: {new, skipped, errors, run_id}
    """
    from reports.scraper import scrape_rekt  # noqa: PLC0415
    from reports.services.dedup_service import is_duplicate  # noqa: PLC0415
    from reports.services.report_service import create_report  # noqa: PLC0415
    from analytics.cleaner import normalize_report  # noqa: PLC0415

    PipelineRun = _get_run_model()

    run = PipelineRun.objects.create(celery_task_id=self.request.id or "")
    logger.info("PipelineRun id=%s started (task=%s)", run.pk, self.request.id)

    # ── 1. Scrape ────────────────────────────────────────────────────────────
    try:
        articles = scrape_rekt(max_pages=max_pages)
    except Exception as exc:
        logger.exception("Scraper failed on run id=%s", run.pk)
        run.error_detail = str(exc)
        run.mark_finished(PipelineRun.Status.FAILED)
        raise self.retry(exc=exc)

    run.scraped_count = len(articles)
    logger.info("Run id=%s — scraped %d articles", run.pk, run.scraped_count)

    # ── 2. Process articles ──────────────────────────────────────────────────
    new_count = 0
    skipped_count = 0
    error_count = 0

    for article in articles:
        url = article.get("source_url", "")

        if is_duplicate(url):
            skipped_count += 1
            logger.debug("Skipped duplicate: %s", url)
            continue

        try:
            with transaction.atomic():
                report = create_report(**article)
                normalize_report(report)
            new_count += 1
        except Exception:
            error_count += 1
            logger.exception("Failed to process article: %s", url)

    # ── 3. Close run ─────────────────────────────────────────────────────────
    run.new_count = new_count
    run.skipped_count = skipped_count
    run.error_count = error_count

    if error_count > 0 and new_count == 0:
        final_status = PipelineRun.Status.FAILED
    elif error_count > 0:
        final_status = PipelineRun.Status.PARTIAL
    else:
        final_status = PipelineRun.Status.SUCCESS

    run.mark_finished(final_status)

    summary = {
        "run_id": run.pk,
        "new": new_count,
        "skipped": skipped_count,
        "errors": error_count,
        "status": final_status,
    }
    logger.info("PipelineRun id=%s finished — %s", run.pk, summary)
    return summary


# ---------------------------------------------------------------------------
# Normalise-unprocessed task (daily catch-up)
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    time_limit=7200,
    name="analytics.tasks.normalize_unprocessed",
)
def normalize_unprocessed(self, batch_size: int = 100) -> dict:
    """
    Daily catch-up: normalise any HackReport records still marked
    is_processed=False (records that errored during run_pipeline).

    Processes in batches to avoid memory pressure on large backlogs.
    Each record is processed atomically.
    """
    from reports.models import HackReport  # noqa: PLC0415
    from analytics.cleaner import normalize_report  # noqa: PLC0415

    qs = HackReport.objects.filter(is_processed=False).order_by("pk")
    total = qs.count()
    logger.info("normalize_unprocessed — %d records to process", total)

    processed = 0
    errors = 0
    offset = 0

    while True:
        batch = list(qs[offset: offset + batch_size])
        if not batch:
            break

        for report in batch:
            try:
                with transaction.atomic():
                    normalize_report(report)
                processed += 1
            except Exception:
                errors += 1
                logger.exception("Failed to normalise report id=%s", report.pk)

        offset += batch_size

    summary = {"processed": processed, "errors": errors, "total": total}
    logger.info("normalize_unprocessed complete — %s", summary)
    return summary


# ---------------------------------------------------------------------------
# Scrape-only task (useful for testing without normalisation)
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    time_limit=1800,
    name="analytics.tasks.scrape_only",
)
def scrape_only(self, max_pages: int = 5) -> dict:
    """
    Scrape rekt.news and store raw records (is_processed=False).
    Does NOT run normalisation — useful for testing the scraper in isolation.
    """
    from reports.scraper import scrape_rekt  # noqa: PLC0415
    from reports.services.dedup_service import is_duplicate  # noqa: PLC0415
    from reports.services.report_service import create_report  # noqa: PLC0415

    try:
        articles = scrape_rekt(max_pages=max_pages)
    except Exception as exc:
        logger.exception("scrape_only: scraper failed")
        raise self.retry(exc=exc)

    new_count = 0
    skipped_count = 0
    error_count = 0

    for article in articles:
        url = article.get("source_url", "")
        if is_duplicate(url):
            skipped_count += 1
            continue
        try:
            with transaction.atomic():
                create_report(**article)
            new_count += 1
        except Exception:
            error_count += 1
            logger.exception("scrape_only: failed to store %s", url)

    return {"new": new_count, "skipped": skipped_count, "errors": error_count}
