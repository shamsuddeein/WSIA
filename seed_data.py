import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "wsia.settings")
django.setup()

from reports.services.report_service import create_report
from reports.services.dedup_service import is_duplicate
from analytics.cleaner import normalize_report

def seed():
    mock_articles = [
        {
            "title": "Euler Finance - Rekt",
            "description": "A flash loan attack on Euler Finance resulted in a loss of $197M.",
            "source_url": "https://rekt.news/euler-rekt/",
            "source": "rekt.news",
            "published_at": "2023-03-14T00:00:00Z",
            "raw_data": {"tags": ["Flash Loan", "DeFi", "Euler"]},
        },
        {
            "title": "Ronin Network - Rekt",
            "description": "Private keys were compromised allowing the attacker to drain $624,000,000 from the bridge.",
            "source_url": "https://rekt.news/ronin-rekt/",
            "source": "rekt.news",
            "published_at": "2022-03-29T00:00:00Z",
            "raw_data": {"tags": ["Bridge", "Access Control Failure"]},
        },
        {
            "title": "Wormhole - Rekt",
            "description": "Signature verification vulnerability allowed minting of 120k wETH ($326M) out of thin air.",
            "source_url": "https://rekt.news/wormhole-rekt/",
            "source": "rekt.news",
            "published_at": "2022-02-03T00:00:00Z",
            "raw_data": {"tags": ["Bridge", "Signature Verification"]},
        },
        {
            "title": "Wintermute - Rekt",
            "description": "A vanity address generation flaw led to a $160M loss in market making funds.",
            "source_url": "https://rekt.news/wintermute-rekt/",
            "source": "rekt.news",
            "published_at": "2022-09-20T00:00:00Z",
            "raw_data": {"tags": ["Cryptography", "Private Key Compromise"]},
        }
    ]

    print("Seeding database with mock Rekt.news data...")
    for article in mock_articles:
        url = article["source_url"]
        if is_duplicate(url):
            print(f"Skipping duplicate: {url}")
            continue
        
        report = create_report(**article)
        normalize_report(report)
        print(f"✅ Processed: {report.title} -> Severity: {report.severity}, Category: {report.category.name if report.category else 'None'}")

if __name__ == "__main__":
    seed()
