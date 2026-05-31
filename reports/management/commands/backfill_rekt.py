import logging
import time

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand, CommandError

from reports.scraper import BASE_URL, HEADERS, REQUEST_DELAY, REQUEST_TIMEOUT, _parse_article
from reports.services.dedup_service import is_duplicate
from reports.services.report_service import create_report

logger = logging.getLogger(__name__)


import xml.etree.ElementTree as ET
from urllib.parse import urlparse

class Command(BaseCommand):
    help = "Backfill historical reports from rekt.news using Sitemap bypass."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-articles",
            type=int,
            default=None,
            help="Optional maximum number of individual articles to scrape.",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=REQUEST_DELAY,
            help=f"Seconds to wait between requests (default: {REQUEST_DELAY}).",
        )

    def handle(self, *args, **options):
        max_articles = options["max_articles"]
        delay = options["delay"]
        new_count = 0
        skipped_count = 0
        error_count = 0

        # Next.js SPA bypass: Fetch the sitemap to get all article URLs!
        sitemap_url = f"{BASE_URL}/sitemap.xml"
        self.stdout.write(f"Fetching sitemap: {sitemap_url}")
        
        # Use browser headers
        browser_headers = HEADERS.copy()
        browser_headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

        try:
            resp = requests.get(sitemap_url, headers=browser_headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except Exception as exc:
            raise CommandError(f"Failed to fetch sitemap: {exc}")

        # Parse XML
        root = ET.fromstring(resp.content)
        namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        
        urls_to_scrape = []
        for url_node in root.findall('ns:url', namespace):
            loc_node = url_node.find('ns:loc', namespace)
            if loc_node is not None and loc_node.text:
                loc = loc_node.text
                # Filter out non-article pages
                parsed = urlparse(loc)
                path = parsed.path.strip('/')
                
                # Exclude root, about, leaderboard, tags
                if path and path not in ['about', 'leaderboard'] and not path.startswith('tag/'):
                    urls_to_scrape.append(loc)

        self.stdout.write(f"Found {len(urls_to_scrape)} potential articles in sitemap.")
        
        # Optionally slice
        if max_articles:
            urls_to_scrape = urls_to_scrape[:max_articles]

        for idx, article_url in enumerate(urls_to_scrape, 1):
            self.stdout.write(f"[{idx}/{len(urls_to_scrape)}] Processing: {article_url}")

            if is_duplicate(article_url):
                skipped_count += 1
                continue

            try:
                art_resp = requests.get(article_url, headers=browser_headers, timeout=REQUEST_TIMEOUT)
                art_resp.raise_for_status()
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"Failed to fetch {article_url}: {exc}"))
                error_count += 1
                continue

            soup = BeautifulSoup(art_resp.text, "lxml")
            
            # Scrape detail page (Next.js static export generates meta tags nicely)
            title = ""
            if title_meta := soup.find("meta", property="og:title"):
                title = title_meta.get("content", "")
            elif h1 := soup.find("h1"):
                title = h1.get_text(strip=True)

            description = ""
            if desc_meta := soup.find("meta", property="og:description"):
                description = desc_meta.get("content", "")
            
            published_at = None
            if pub_meta := soup.find("meta", property="article:published_time"):
                from reports.scraper import _parse_date
                published_at = _parse_date(pub_meta.get("content", ""))
                
            if not title:
                self.stderr.write(self.style.WARNING(f"Skipping {article_url} - No title found."))
                skipped_count += 1
                continue

            article_data = {
                "title": title,
                "description": description,
                "source_url": article_url,
                "source": "rekt.news",
                "published_at": published_at,
                "raw_data": {
                    "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "tags": [], # Detailed tags might require more complex selectors on detail page
                },
            }

            try:
                create_report(**article_data)
                new_count += 1
                self.stdout.write(self.style.SUCCESS(f"  Saved new report: {title}"))
            except Exception as exc:
                error_count += 1
                self.stderr.write(self.style.ERROR(f"  Error storing {article_url}: {exc}"))

            time.sleep(delay)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill complete! New: {new_count}, Skipped: {skipped_count}, Errors: {error_count}"
            )
        )
