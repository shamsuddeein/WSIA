import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from reports.models import HackReport
from analytics.cleaner import normalize_report
import os
import django
import concurrent.futures

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wsia.settings')
django.setup()

class Command(BaseCommand):
    help = "Scrape the full article description from rekt.news for uncategorised reports to improve category matching."

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0)
        parser.add_argument('--database', type=str, default='default')

    def fetch_and_parse(self, session, report):
        try:
            resp = session.get(report.source_url, timeout=30)
            if resp.status_code == 200:
                html = resp.text
                soup = BeautifulSoup(html, 'html.parser')
                paragraphs = soup.select('section.post-content p')
                if paragraphs:
                    text_parts = []
                    for p in paragraphs:
                        text = p.get_text(strip=True)
                        if len(text) > 20:
                            text_parts.append(text)
                            if len(text_parts) >= 30: # Get up to 30 paragraphs
                                break
                    if text_parts:
                        new_desc = "\n\n".join(text_parts)
                        return report, new_desc
        except Exception as e:
            pass
        return report, None

    def process_all(self, reports):
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            futures = {executor.submit(self.fetch_and_parse, session, report): report for report in reports}
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())
        return results

    def handle(self, *args, **options):
        db = options['database']
        reports = list(HackReport.objects.using(db).filter(
            category__isnull=True, 
            source_url__icontains='rekt.news/'
        ))

        self.stdout.write(f"Starting async Option A background job: fetching descriptions for {len(reports)} uncategorised reports...")

        results = self.process_all(reports)

        updated = 0
        for report, new_desc in results:
            if new_desc:
                report.description = new_desc
                report.category = None
                normalize_report(report)
                updated += 1
                self.stdout.write(self.style.SUCCESS(f"  -> {report.source_url}: Extracted text & normalised. New category: {report.category}"))
            else:
                self.stdout.write(self.style.WARNING(f"  -> {report.source_url}: Failed or no content."))

        self.stdout.write(self.style.SUCCESS(f"\nDone! Enriched and reprocessed {updated} reports."))
