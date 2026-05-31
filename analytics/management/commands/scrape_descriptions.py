import time
import requests
import logging
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from reports.models import HackReport
from analytics.cleaner import normalize_report

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Scrape the full article description from rekt.news for uncategorised reports to improve category matching."

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Limit the number of records to process (0 for all)',
        )
        parser.add_argument(
            '--database',
            type=str,
            default='default',
            help='The database to process (e.g. default for postgres, or sqlite)',
        )

    def handle(self, *args, **options):
        db = options['database']
        limit = options['limit']

        # Get uncategorized reports that haven't had their descriptions fetched yet
        # If the description is empty or doesn't seem like the full text, we can scrape.
        # For simplicity, we just filter by category__isnull=True and where source_url is valid.
        reports = HackReport.objects.using(db).filter(
            category__isnull=True, 
            source_url__icontains='rekt.news/'
        ).order_by('-created_at')

        if limit > 0:
            reports = reports[:limit]

        self.stdout.write(f"Starting Option A background job: fetching descriptions for {reports.count()} uncategorised reports on DB '{db}'...")

        updated = 0
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
        })

        for report in reports:
            self.stdout.write(f"Fetching {report.source_url}...")
            try:
                resp = session.get(report.source_url, timeout=10)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    
                    # rekt.news posts are typically inside article or standard div blocks.
                    # We grab paragraphs inside the main content area.
                    content_div = soup.find('div', class_='post-content') or soup.find('article')
                    if content_div:
                        paragraphs = content_div.find_all('p')
                        # Extract the first 3-5 substantive paragraphs
                        text_parts = []
                        for p in paragraphs:
                            text = p.get_text(strip=True)
                            if len(text) > 20:  # Skip short snippets
                                text_parts.append(text)
                                if len(text_parts) >= 4:
                                    break
                                    
                        if text_parts:
                            new_desc = "\n\n".join(text_parts)
                            report.description = new_desc
                            # Temporarily nullify the category so normalize_report can recalculate
                            report.category = None
                            
                            # Re-run normalisation (which also saves)
                            normalize_report(report)
                            updated += 1
                            self.stdout.write(self.style.SUCCESS(f"  -> Extracted text & normalised. New category: {report.category}"))
                        else:
                            self.stdout.write(self.style.WARNING("  -> No paragraphs found."))
                    else:
                        self.stdout.write(self.style.WARNING("  -> Could not find main content div."))
                else:
                    self.stdout.write(self.style.ERROR(f"  -> HTTP {resp.status_code}"))
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  -> Failed: {e}"))
                
            time.sleep(2)  # Be respectful to rekt.news servers

        self.stdout.write(self.style.SUCCESS(f"\nDone! Enriched and reprocessed {updated} reports."))
