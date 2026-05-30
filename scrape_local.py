import os
import sys
import django
from bs4 import BeautifulSoup

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "wsia.settings")
django.setup()

from reports.scraper import _parse_article
from reports.services.report_service import create_report
from reports.services.dedup_service import is_duplicate
from analytics.cleaner import normalize_report

def run(html_path):
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("article.post")
    print(f"Found {len(cards)} articles in {html_path}")
    
    new_count = 0
    for card in cards:
        article = _parse_article(card)
        if not article: continue
        
        url = article["source_url"]
        if is_duplicate(url):
            print(f"Skipping duplicate: {url}")
            continue
            
        try:
            report = create_report(**article)
            normalize_report(report)
            print(f"Created: {report.title} ({report.severity})")
            new_count += 1
        except Exception as e:
            print(f"Error on {url}: {e}")
            
    print(f"Successfully processed {new_count} new reports.")

if __name__ == "__main__":
    run(sys.argv[1])
