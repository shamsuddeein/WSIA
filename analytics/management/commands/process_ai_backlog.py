import time
from django.core.management.base import BaseCommand
from django.db.models import Q
from reports.models import HackReport
from analytics.tasks import enrich_report_with_ai
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wsia.settings')
django.setup()

class Command(BaseCommand):
    help = "Process a batch of reports to generate AI summaries and embeddings."

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=50, help='Number of records to process in this run.')
        parser.add_argument('--database', type=str, default='default')

    def handle(self, *args, **options):
        db = options['database']
        limit = options['limit']

        if not os.environ.get("OPENAI_API_KEY"):
            self.stdout.write(self.style.ERROR("OPENAI_API_KEY is not set. Cannot run AI backfill."))
            return

        # Find processed reports missing either summary or embedding
        reports = list(HackReport.objects.using(db).filter(
            is_processed=True
        ).filter(
            Q(ai_summary__isnull=True) | Q(embedding__isnull=True)
        ).order_by('-created_at')[:limit])

        if not reports:
            self.stdout.write(self.style.SUCCESS("No reports need AI enrichment!"))
            return

        self.stdout.write(f"Starting AI backfill for {len(reports)} reports (limit={limit})...")

        success_count = 0
        error_count = 0

        for report in reports:
            self.stdout.write(f"Processing report {report.id}: {report.title}")
            
            # Since this is a batch script for backlog, we process synchronously here
            # to avoid flooding celery and to respect rate limits sequentially if needed
            # Or we can just call the task. We'll call the task synchronously for simplicity and reliability.
            result = enrich_report_with_ai(report.id)
            
            if result.get("status") == "success":
                success_count += 1
                self.stdout.write(self.style.SUCCESS(f"  -> Successfully enriched report {report.id}"))
            elif result.get("status") == "no_change":
                self.stdout.write(self.style.WARNING(f"  -> No change for report {report.id}"))
            else:
                error_count += 1
                self.stdout.write(self.style.ERROR(f"  -> Failed to enrich report {report.id}"))
                
            # Optional: Sleep slightly to avoid blasting OpenAI rate limits if chunk is large
            time.sleep(0.5)

        self.stdout.write(self.style.SUCCESS(f"\nDone! Enriched {success_count} reports. Errors: {error_count}"))
