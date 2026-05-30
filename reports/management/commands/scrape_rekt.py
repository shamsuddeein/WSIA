"""
Management command: scrape_rekt

Runs the rekt.news scraper, deduplicates, and stores raw records.

Usage:
    python manage.py scrape_rekt
    python manage.py scrape_rekt --max-pages 3
    python manage.py scrape_rekt --dry-run
"""

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Scrape rekt.news and store new HackReport records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-pages",
            type=int,
            default=5,
            help="Maximum number of listing pages to scrape (default: 5).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and print articles without writing to the database.",
        )

    def handle(self, *args, **options):
        from reports.scraper import scrape_rekt
        from reports.services.dedup_service import is_duplicate
        from reports.services.report_service import create_report

        max_pages = options["max_pages"]
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no records will be written."))

        self.stdout.write(f"Scraping rekt.news (max_pages={max_pages})...")

        try:
            articles = scrape_rekt(max_pages=max_pages)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Scraper failed: {exc}"))
            return

        new_count = 0
        skipped_count = 0
        error_count = 0

        for article in articles:
            url = article["source_url"]

            if is_duplicate(url):
                skipped_count += 1
                continue

            if dry_run:
                self.stdout.write(f"  [DRY RUN] Would create: {article['title']!r}")
                new_count += 1
                continue

            try:
                report = create_report(**article)
                self.stdout.write(
                    self.style.SUCCESS(f"  Created [{report.pk}]: {report.title}")
                )
                new_count += 1
            except Exception as exc:
                error_count += 1
                self.stderr.write(
                    self.style.ERROR(f"  Error storing {url!r}: {exc}")
                )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done — new: {new_count}, skipped: {skipped_count}, errors: {error_count}"
            )
        )
