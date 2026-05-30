import os
import django
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "wsia.settings")
django.setup()

from reports.models import HackReport
from analytics.tasks import enrich_report_with_ai
from analytics.ai_service import get_client

def run_live_test():
    client = get_client()
    if not client:
        print("FAIL: No valid OpenAI client.")
        return
        
    print(f"OpenAI Client configured with key starting: {client.api_key[:10]}...")
    
    # Pick a report that doesn't have a summary yet
    report = HackReport.objects.filter(ai_summary__isnull=True).first()
    if not report:
        print("No reports found to enrich. Seeding one...")
        from reports.services.report_service import create_report
        report = create_report(
            title="Live AI Test Report",
            description="On May 30th, the Live AI protocol suffered a massive vulnerability where an attacker exploited a reentrancy flaw in the staking contract. The attacker drained $5,000,000 in ETH and bridged it to Tornado Cash. The team has paused the protocol.",
            source_url="https://rekt.news/live-ai-test",
            source="rekt.news",
        )
        report.is_processed = True
        report.save()
        
    print(f"Enriching Report #{report.id}: {report.title}")
    
    # Run synchronously
    result = enrich_report_with_ai(report.id)
    print(f"Task Result: {result}")
    
    report.refresh_from_db()
    print("\n--- GENERATED SUMMARY ---")
    print(report.ai_summary)
    
    print("\n--- GENERATED EMBEDDING ---")
    if report.embedding:
        print(f"Vector of {len(report.embedding)} dimensions. First 5 values: {report.embedding[:5]}")
    else:
        print("None")
        
    print("\n✅ Live test complete.")

if __name__ == "__main__":
    run_live_test()
