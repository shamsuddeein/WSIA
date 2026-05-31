import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wsia.settings')
django.setup()

from reports.models import HackReport, Category
from reports.services.category_service import assign_category_from_tags

reports = HackReport.objects.filter(category__isnull=True).prefetch_related('tags')
print(f"Checking {reports.count()} uncategorized reports...")

updated_count = 0
for report in reports:
    cat = assign_category_from_tags(report)
    if cat:
        report.category = cat
        report.save(update_fields=['category'])
        updated_count += 1

total_categorized = HackReport.objects.filter(category__isnull=False).count()
total = HackReport.objects.count()
percent = (total_categorized / total) * 100 if total > 0 else 0
print(f"Updated {updated_count}. Total categorised: {total_categorized}/{total} ({percent:.1f}%)")
