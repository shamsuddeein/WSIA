import ast
import json
import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand, CommandError

from reports.scraper import BASE_URL, HEADERS, REQUEST_DELAY, REQUEST_TIMEOUT, _parse_article, _parse_date
from reports.services.dedup_service import is_duplicate
from reports.services.report_service import create_report

logger = logging.getLogger(__name__)

BROWSER_HEADERS = {
    **HEADERS,
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


class Command(BaseCommand):
    help = "Backfill historical reports from rekt.news."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-articles",
            type=int,
            default=None,
            help="Optional maximum number of articles to store.",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=REQUEST_DELAY,
            help=f"Seconds to wait between stored articles (default: {REQUEST_DELAY}).",
        )

    def handle(self, *args, **options):
        max_articles = options["max_articles"]
        delay = options["delay"]

        if max_articles is not None and max_articles < 0:
            raise CommandError("--max-articles must be 0 or greater.")

        try:
            articles = self._load_articles()
        except requests.exceptions.RequestException as exc:
            raise CommandError(f"Failed to fetch rekt.news index: {exc}") from exc

        if max_articles is not None:
            articles = articles[:max_articles]

        self.stdout.write(f"Found {len(articles)} candidate articles.")

        new_count = 0
        skipped_count = 0
        error_count = 0

        for idx, article in enumerate(articles, 1):
            article_url = article["source_url"]
            self.stdout.write(f"[{idx}/{len(articles)}] Processing: {article_url}")

            if is_duplicate(article_url):
                skipped_count += 1
                continue

            try:
                report = create_report(**article)
                self.stdout.write(self.style.SUCCESS(f"  Created [{report.pk}]: {report.title}"))
                new_count += 1
            except Exception as exc:
                error_count += 1
                self.stderr.write(self.style.ERROR(f"  Error storing {article_url}: {exc}"))

            if idx < len(articles):
                time.sleep(delay)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill complete! New: {new_count}, Skipped: {skipped_count}, Errors: {error_count}"
            )
        )

    def _load_articles(self):
        self.stdout.write(f"Fetching index: {BASE_URL}")
        index_resp = requests.get(BASE_URL, headers=BROWSER_HEADERS, timeout=REQUEST_TIMEOUT)
        index_resp.raise_for_status()

        soup = BeautifulSoup(index_resp.text, "lxml")
        articles = self._articles_from_next_bundle(soup)
        if articles:
            self.stdout.write("Loaded article metadata from Next.js bundle.")
            return articles

        self.stdout.write("Bundle metadata unavailable; falling back to homepage cards.")
        return self._articles_from_cards(soup)

    def _articles_from_next_bundle(self, soup):
        script_urls = []
        for script in soup.select('script[src*="/_next/static/"]'):
            src = script.get("src", "")
            if "/pages/_app-" in src or "/pages/index-" in src:
                script_urls.append(urljoin(BASE_URL, src))

        for script_url in script_urls:
            try:
                resp = requests.get(script_url, headers=BROWSER_HEADERS, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
            except requests.exceptions.RequestException as exc:
                logger.warning("Could not fetch %s: %s", script_url, exc)
                continue

            posts = self._extract_english_posts(resp.text)
            if posts:
                return [self._article_from_bundle_post(post) for post in posts]

        return []

    def _extract_english_posts(self, script_text):
        candidates = []
        for raw_payload in _iter_json_parse_payloads(script_text):
            try:
                payload = json.loads(raw_payload)
            except json.JSONDecodeError:
                continue

            posts = payload.get("posts") if isinstance(payload, dict) else None
            if not isinstance(posts, list):
                continue

            article_posts = [
                post for post in posts
                if isinstance(post, dict) and post.get("slug") and post.get("title")
            ]
            if not article_posts:
                continue

            candidates.append(article_posts)

        if not candidates:
            return []

        # The bundle contains several locale files. Prefer the largest mostly-English list.
        def score(posts):
            sample_titles = [str(post.get("title", "")) for post in posts[:20]]
            englishish = sum(_is_mostly_ascii(title) for title in sample_titles)
            return (englishish, len(posts))

        return max(candidates, key=score)

    def _article_from_bundle_post(self, post):
        source_url = urljoin(f"{BASE_URL}/", str(post["slug"]).strip("/"))
        return {
            "title": str(post["title"]).strip(),
            "description": str(post.get("excerpt") or "").strip(),
            "source_url": source_url,
            "source": "rekt.news",
            "published_at": _parse_bundle_date(str(post.get("date") or "")),
            "raw_data": {
                "scraped_at": datetime.now(tz=timezone.utc).isoformat(),
                "tags": post.get("tags") if isinstance(post.get("tags"), list) else [],
                "source": "next_bundle",
            },
        }

    def _articles_from_cards(self, soup):
        articles = []
        for card in soup.select("article.post"):
            article = _parse_article(card)
            if article:
                article["raw_data"]["source"] = "homepage_cards"
                articles.append(article)
        return articles


def _iter_json_parse_payloads(script_text):
    for match in re.finditer(r"JSON\.parse\('((?:\\.|[^'])*)'\)", script_text):
        try:
            yield ast.literal_eval(f"'{match.group(1)}'")
        except (SyntaxError, ValueError):
            continue


def _is_mostly_ascii(value):
    if not value:
        return False
    ascii_chars = sum(ord(char) < 128 for char in value)
    return ascii_chars / len(value) >= 0.8


def _parse_bundle_date(value):
    parsed = _parse_date(value)
    if parsed is not None:
        return parsed

    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
