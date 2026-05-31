import logging
import time

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand, CommandError

from reports.scraper import BASE_URL, HEADERS, REQUEST_DELAY, REQUEST_TIMEOUT, _parse_article
from reports.services.dedup_service import is_duplicate
from reports.services.report_service import create_report

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfill historical reports from rekt.news."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-pages",
            type=int,
            default=None,
            help="Optional maximum number of listing pages to scrape.",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=REQUEST_DELAY,
            help=f"Seconds to wait between page requests (default: {REQUEST_DELAY}).",
        )

    def handle(self, *args, **options):
        max_pages = options["max_pages"]
        delay = options["delay"]
        new_count = 0
        skipped_count = 0
        error_count = 0
        page_num = 1
        
        # Cloudflare aggressive cache bypass
        browser_headers = HEADERS.copy()
        browser_headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

        while max_pages is None or page_num <= max_pages:
            self.stdout.write(f"Scraping page {page_num}...")
            url = BASE_URL if page_num == 1 else f"{BASE_URL}/page/{page_num}/"

            try:
                resp = requests.get(url, headers=browser_headers, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
            except requests.exceptions.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code == 404 and page_num > 1:
                    self.stdout.write(f"Page {page_num} returned 404; stopping pagination.")
                    break
                error_count += 1
                raise CommandError(f"Failed to fetch page {page_num}: {exc}") from exc
            except requests.exceptions.RequestException as exc:
                error_count += 1
                raise CommandError(f"Failed to fetch page {page_num}: {exc}") from exc

            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select("article.post")

            if not cards:
                self.stdout.write(f"No article cards found on page {page_num}; stopping pagination.")
                break

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

            page_num += 1

            # Polite delay before hitting the next page
            if max_pages is None or page_num <= max_pages:
                time.sleep(delay)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill complete! New: {new_count}, Skipped: {skipped_count}, Errors: {error_count}"
            )
        )
