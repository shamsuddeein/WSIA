"""
Phase 5 tests — Celery task logic, PipelineRun auditing,
and pipeline integration using mocked scraper/network.

Run with:
    python manage.py test analytics.tests_phase5 --verbosity=2
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from core.models import PipelineRun
from reports.models import Category, HackReport, Tag
from reports.services.dedup_service import compute_hash

# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

def _article(n: int, **kwargs) -> dict:
    """Return a minimal article dict for testing."""
    base = {
        "title": f"Test Exploit #{n}",
        "description": f"Attacker drained $5 million from protocol {n}.",
        "source_url": f"https://rekt.news/exploit-{n}",
        "source": "rekt.news",
        "published_at": None,
        "raw_data": {"tags": ["DeFi"], "scraped_at": "2026-05-30T00:00:00Z"},
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# PipelineRun model
# ---------------------------------------------------------------------------

class PipelineRunModelTests(TestCase):

    def test_creates_with_running_status(self):
        run = PipelineRun.objects.create()
        self.assertEqual(run.status, PipelineRun.Status.RUNNING)
        self.assertIsNone(run.finished_at)

    def test_mark_finished_sets_timestamps(self):
        run = PipelineRun.objects.create()
        run.mark_finished(PipelineRun.Status.SUCCESS)
        run.refresh_from_db()
        self.assertEqual(run.status, PipelineRun.Status.SUCCESS)
        self.assertIsNotNone(run.finished_at)

    def test_str_representation(self):
        run = PipelineRun.objects.create()
        self.assertIn("RUNNING", str(run).upper())

    def test_str_with_duration(self):
        run = PipelineRun.objects.create()
        run.mark_finished(PipelineRun.Status.SUCCESS)
        run.refresh_from_db()
        s = str(run)
        self.assertIn("success", s.lower())

    def test_counter_defaults_zero(self):
        run = PipelineRun.objects.create()
        self.assertEqual(run.new_count, 0)
        self.assertEqual(run.skipped_count, 0)
        self.assertEqual(run.error_count, 0)
        self.assertEqual(run.scraped_count, 0)


# ---------------------------------------------------------------------------
# run_pipeline task — unit tests with mocked scraper
# ---------------------------------------------------------------------------

class RunPipelineTaskTests(TestCase):

    def _call_task(self, articles):
        """Invoke run_pipeline.run() bypassing Celery broker."""
        from analytics.tasks import run_pipeline

        # Patch the scraper so no network call is made
        with patch("reports.scraper.scrape_rekt", return_value=articles):
            # run() calls the task synchronously
            return run_pipeline.run(max_pages=1)

    def test_new_records_created(self):
        result = self._call_task([_article(1), _article(2)])
        self.assertEqual(result["new"], 2)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(HackReport.objects.count(), 2)

    def test_duplicate_articles_skipped(self):
        # Pre-insert one record
        url = _article(1)["source_url"]
        HackReport.objects.create(
            title="Existing",
            description="",
            source_url=url,
            source="rekt.news",
            hash=compute_hash(url),
        )
        result = self._call_task([_article(1), _article(2)])
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["new"], 1)
        self.assertEqual(HackReport.objects.count(), 2)

    def test_running_twice_produces_no_duplicates(self):
        """Core phase 5 acceptance criterion from the build plan."""
        articles = [_article(i) for i in range(1, 4)]
        self._call_task(articles)
        self._call_task(articles)   # second run — all should be skipped
        self.assertEqual(HackReport.objects.count(), 3)

    def test_records_are_normalised_after_pipeline(self):
        result = self._call_task([_article(1)])
        self.assertEqual(result["new"], 1)
        report = HackReport.objects.get()
        self.assertTrue(report.is_processed)
        self.assertEqual(report.severity, "high")  # $5M → high

    def test_pipelinerun_audit_record_created(self):
        self._call_task([_article(1)])
        self.assertEqual(PipelineRun.objects.count(), 1)
        run = PipelineRun.objects.get()
        self.assertEqual(run.status, PipelineRun.Status.SUCCESS)
        self.assertIsNotNone(run.finished_at)
        self.assertEqual(run.new_count, 1)

    def test_pipelinerun_partial_on_some_errors(self):
        from analytics.tasks import run_pipeline
        from reports.services import report_service

        good = _article(1)
        bad = _article(2)

        call_count = {"n": 0}
        original_create = report_service.create_report

        def patched_create(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise ValueError("Simulated DB error")
            return original_create(**kwargs)

        with patch("reports.scraper.scrape_rekt", return_value=[good, bad]):
            with patch("reports.services.report_service.create_report", side_effect=patched_create):
                result = self._call_task([good, bad])

        run = PipelineRun.objects.get()
        self.assertEqual(run.status, PipelineRun.Status.PARTIAL)
        self.assertEqual(run.error_count, 1)
        self.assertEqual(result["new"], 1)

    def test_pipelinerun_failed_status_when_all_error(self):
        from analytics.tasks import run_pipeline
        from reports.services import report_service

        with patch("reports.scraper.scrape_rekt", return_value=[_article(1), _article(2)]):
            with patch(
                "reports.services.report_service.create_report",
                side_effect=ValueError("Simulated DB error"),
            ):
                run_pipeline.run(max_pages=1)

        run = PipelineRun.objects.get()
        self.assertEqual(run.status, PipelineRun.Status.FAILED)

    def test_scraper_failure_marks_run_failed(self):
        from analytics.tasks import run_pipeline

        with patch("reports.scraper.scrape_rekt", side_effect=ConnectionError("down")):
            with self.assertRaises(Exception):
                run_pipeline.run(max_pages=1)

        run = PipelineRun.objects.get()
        self.assertEqual(run.status, PipelineRun.Status.FAILED)

    def test_tags_synced_from_raw_data(self):
        article = _article(1)
        article["raw_data"]["tags"] = ["Flash Loan", "DeFi"]
        self._call_task([article])
        report = HackReport.objects.get()
        tag_names = set(report.tags.values_list("name", flat=True))
        self.assertIn("Flash Loan", tag_names)
        self.assertIn("DeFi", tag_names)


# ---------------------------------------------------------------------------
# normalize_unprocessed task
# ---------------------------------------------------------------------------

class NormalizeUnprocessedTaskTests(TestCase):

    def _make_raw_report(self, n: int) -> HackReport:
        url = f"https://rekt.news/raw-{n}"
        return HackReport.objects.create(
            title=f"  <b>Raw Report {n}</b>  ",
            description=f"Flash loan attack drained $10 million from pool {n}.",
            source_url=url,
            source="rekt.news",
            hash=compute_hash(url),
            is_processed=False,
            raw_data={"tags": [f"Tag{n}"]},
        )

    def test_processes_unprocessed_records(self):
        from analytics.tasks import normalize_unprocessed

        for i in range(3):
            self._make_raw_report(i)

        result = normalize_unprocessed.run()
        self.assertEqual(result["processed"], 3)
        self.assertEqual(result["errors"], 0)

        for report in HackReport.objects.all():
            self.assertTrue(report.is_processed)

    def test_skips_already_processed_records(self):
        from analytics.tasks import normalize_unprocessed

        url = "https://rekt.news/already-done"
        HackReport.objects.create(
            title="Done",
            description="Already clean.",
            source_url=url,
            source="rekt.news",
            hash=compute_hash(url),
            is_processed=True,
        )

        result = normalize_unprocessed.run()
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["processed"], 0)

    def test_empty_queue_returns_zero_counts(self):
        from analytics.tasks import normalize_unprocessed
        result = normalize_unprocessed.run()
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["processed"], 0)
        self.assertEqual(result["errors"], 0)


# ---------------------------------------------------------------------------
# scrape_only task
# ---------------------------------------------------------------------------

class ScrapeOnlyTaskTests(TestCase):

    def test_stores_raw_records(self):
        from analytics.tasks import scrape_only

        with patch("reports.scraper.scrape_rekt", return_value=[_article(1), _article(2)]):
            result = scrape_only.run(max_pages=1)

        self.assertEqual(result["new"], 2)
        self.assertEqual(HackReport.objects.count(), 2)
        # Should NOT have been normalised
        for r in HackReport.objects.all():
            self.assertFalse(r.is_processed)

    def test_deduplicates_on_second_call(self):
        from analytics.tasks import scrape_only

        articles = [_article(1)]
        with patch("reports.scraper.scrape_rekt", return_value=articles):
            scrape_only.run()
            result = scrape_only.run()

        self.assertEqual(result["skipped"], 1)
        self.assertEqual(HackReport.objects.count(), 1)
