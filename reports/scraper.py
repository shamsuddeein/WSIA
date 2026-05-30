"""
rekt.news scraper — Phase 3.

Extracts security incident reports from https://rekt.news.
Rate-limited. Respects robots.txt intent.
"""

import logging
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SOURCE_NAME = "rekt.news"
BASE_URL = "https://rekt.news"
REQUEST_TIMEOUT = 10          # seconds before raising Timeout
REQUEST_DELAY = 2             # seconds between requests
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; WSIA-bot/1.0; "
        "+https://github.com/wsia-project)"
    )
}


def _get(url: str) -> requests.Response:
    """HTTP GET with timeout and a polite User-Agent."""
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp


def scrape_rekt() -> list[dict]:
    """
    Scrape the rekt.news listing page and return a list of article dicts.

    Each dict contains the keys expected by report_service.create_report():
        title, description, source_url, source, raw_data, published_at
    """
    logger.info("Scraping %s", BASE_URL)
    resp = _get(BASE_URL)
    soup = BeautifulSoup(resp.text, "lxml")

    articles = []

    # rekt.news renders articles as <article> or <a> elements — adjust
    # selectors if the site structure changes.
    for item in soup.select("article, .post-card, .article-item"):
        try:
            title_el = item.select_one("h1, h2, h3, .title")
            link_el = item.select_one("a[href]")
            desc_el = item.select_one("p, .excerpt, .description")

            if not title_el or not link_el:
                continue

            title = title_el.get_text(strip=True)
            href = link_el["href"]
            source_url = href if href.startswith("http") else f"{BASE_URL}{href}"
            description = desc_el.get_text(strip=True) if desc_el else ""

            # Do NOT store: author names, full article body, cookies, tokens
            articles.append(
                {
                    "title": title,
                    "description": description,
                    "source_url": source_url,
                    "source": SOURCE_NAME,
                    "published_at": None,   # parse date from item if available
                    "raw_data": {
                        "scraped_at": datetime.utcnow().isoformat(),
                    },
                }
            )

            time.sleep(REQUEST_DELAY)

        except Exception:
            logger.exception("Failed to parse article item")
            continue

    logger.info("Scraped %d articles from %s", len(articles), SOURCE_NAME)
    return articles
