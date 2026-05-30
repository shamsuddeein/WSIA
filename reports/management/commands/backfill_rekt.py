import logging
import time
import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from reports.scraper import _parse_article, HEADERS, REQUEST_TIMEOUT
from reports.services.dedup_service import is_duplicate
from reports.services.report_service import create_report

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Backfill all historical reports from rekt.news (42 pages)."

    def handle(self, *args, **kwargs):
        base_url = "https://rekt.news/?page="
        new_count = 0
        skipped_count = 0
        error_count = 0

        # Loop through all 42 pages deterministically
        for page_num in range(1, 43):
            self.stdout.write(f"Scraping page {page_num}...")
            url = f"{base_url}{page_num}"
            
            try:
                resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"Failed to fetch page {page_num}: {exc}"))
                continue

            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select("article.post")

            if not cards:
                self.stdout.write(f"No article cards found on page {page_num}, moving to next.")
                continue

            for card in cards:
                article = _parse_article(card)
                if not article:
                    continue

                article_url = article["source_url"]

                # Idempotent deduplication check
                if is_duplicate(article_url):
                    skipped_count += 1
                    continue

                try:
                    report = create_report(**article)
                    self.stdout.write(self.style.SUCCESS(f"  Created [{report.pk}]: {report.title}"))
                    new_count += 1
                except Exception as exc:
                    error_count += 1
                    self.stderr.write(self.style.ERROR(f"  Error storing {article_url!r}: {exc}"))

            # Polite delay before hitting the next page
            time.sleep(2)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill complete! New: {new_count}, Skipped: {skipped_count}, Errors: {error_count}"
            )
        )
