"""
rekt.news scraper — Phase 3.

Selectors verified against live site (2026-05-30):
  article card  →  article.post
  title + link  →  .post-title a
  excerpt       →  .post-excerpt p
  date          →  .post-meta time
  tags          →  .post-meta a[href*="tag="]

Hrefs are relative (e.g. /poisoned-pipeline) — resolved against BASE_URL.
"""

import logging
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SOURCE_NAME = "rekt.news"
BASE_URL = "https://rekt.news"
REQUEST_TIMEOUT = 15          # seconds
REQUEST_DELAY = 2             # seconds between page requests
MAX_PAGES = 5                 # safety cap — increase once pipeline is stable
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; WSIA-bot/1.0; "
        "+https://github.com/wsia-project)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get(url: str) -> requests.Response:
    """GET with timeout, polite User-Agent, and raise on 4xx/5xx."""
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_article(card) -> dict | None:
    """
    Extract a single article dict from an `article.post` BeautifulSoup tag.
    Returns None if any required field is missing.
    """
    try:
        # Title + link
        title_el = card.select_one(".post-title a")
        if not title_el:
            return None

        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")
        if not href:
            return None

        # Resolve relative → absolute URL
        source_url = urljoin(BASE_URL, href)

        # Excerpt / description
        excerpt_el = card.select_one(".post-excerpt p") or card.select_one(".post-excerpt")
        description = excerpt_el.get_text(strip=True) if excerpt_el else ""

        # Published date
        published_at = None
        time_el = card.select_one(".post-meta time")
        if time_el:
            # Prefer machine-readable datetime attribute
            dt_str = time_el.get("datetime") or time_el.get_text(strip=True)
            if dt_str:
                try:
                    published_at = _parse_date(dt_str)
                except (ValueError, OverflowError):
                    logger.debug("Could not parse date: %r", dt_str)

        # Tags from .post-meta links (e.g. /?tag=Flash+Loan)
        scraped_tags = []
        for tag_el in card.select('.post-meta a[href*="tag="]'):
            href_tag = tag_el.get("href", "")
            qs = parse_qs(urlparse(href_tag).query)
            tag_values = qs.get("tag", [])
            scraped_tags.extend(tag_values)

        return {
            "title": title,
            "description": description,
            "source_url": source_url,
            "source": SOURCE_NAME,
            "published_at": published_at,
            "raw_data": {
                "scraped_at": datetime.now(tz=timezone.utc).isoformat(),
                "tags": scraped_tags,
            },
        }

    except Exception:
        logger.exception("Failed to parse article card")
        return None


def _parse_date(value: str) -> datetime | None:
    """
    Try to parse a date string into a timezone-aware datetime.
    Handles ISO 8601 and common human-readable formats.
    """
    if not value:
        return None

    formats = [
        "%Y-%m-%dT%H:%M:%S%z",     # ISO 8601 with tz
        "%Y-%m-%dT%H:%M:%SZ",      # ISO 8601 UTC
        "%Y-%m-%d",                 # date-only
        "%A, %B %d, %Y",           # e.g. Friday, May 29, 2026
        "%B %d, %Y",               # e.g. May 29, 2026
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(value.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Main scrape function
# ---------------------------------------------------------------------------

def scrape_rekt(max_pages: int = MAX_PAGES) -> list[dict]:
    """
    Scrape the rekt.news listing pages and return article dicts.

    Paginates up to `max_pages` pages. Each dict is ready to be passed
    directly to report_service.create_report() after is_duplicate() check.

    What is NOT stored (per build plan):
      - Author names or personal details
      - Copyrighted full article body text
      - Raw cookies, session tokens, or auth data
    """
    articles: list[dict] = []
    page = 1

    while page <= max_pages:
        url = BASE_URL if page == 1 else f"{BASE_URL}/page/{page}/"
        logger.info("Scraping page %d: %s", page, url)

        try:
            resp = _get(url)
        except requests.exceptions.Timeout:
            logger.warning("Timeout on page %d — stopping pagination", page)
            break
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                logger.info("Page %d returned 404 — no more pages", page)
            else:
                logger.error("HTTP error on page %d: %s", page, exc)
            break
        except requests.exceptions.RequestException as exc:
            logger.error("Request failed on page %d: %s", page, exc)
            break

        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.select("article.post")

        if not cards:
            logger.info("No article cards found on page %d — stopping", page)
            break

        page_articles = []
        for card in cards:
            article = _parse_article(card)
            if article:
                page_articles.append(article)

        logger.info("Page %d: found %d articles", page, len(page_articles))
        articles.extend(page_articles)

        # Polite delay before next page
        if page < max_pages:
            time.sleep(REQUEST_DELAY)

        page += 1

    logger.info("Scrape complete — total articles: %d", len(articles))
    return articles
