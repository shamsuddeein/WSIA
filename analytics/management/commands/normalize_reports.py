"""
Management command: normalize_reports

Runs Phase 4 cleaning and normalization over all unprocessed HackReports.

Usage:
    python manage.py normalize_reports
    python manage.py normalize_reports --batch-size 50
    python manage.py normalize_reports --report-id 42
    python manage.py normalize_reports --dry-run
"""

import logging

from django.core.management.base import BaseCommand
from django.db import transaction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Normalize all unprocessed HackReport records (Phase 4)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of records to process per DB batch (default: 100).",
        )
        parser.add_argument(
            "--report-id",
            type=int,
            default=None,
            help="Normalize a single specific report by ID.",
        )
        parser.add_argument(
            "--reprocess",
            action="store_true",
            help="Re-run normalization even on already-processed reports.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would happen without writing to the database.",
        )
        parser.add_argument(
            "--database",
            type=str,
            default="default",
            help="Database to use.",
        )

    def handle(self, *args, **options):
        from reports.models import HackReport
        from analytics.cleaner import normalize_report

        dry_run = options["dry_run"]
        batch_size = options["batch_size"]
        report_id = options["report_id"]
        reprocess = options["reprocess"]
        db = options["database"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no records will be written.\n"))

        # Build queryset
        if report_id:
            qs = HackReport.objects.using(db).filter(pk=report_id)
            if not qs.exists():
                self.stderr.write(self.style.ERROR(f"No HackReport with id={report_id}"))
                return
        else:
            qs = HackReport.objects.using(db).all() if reprocess else HackReport.objects.using(db).filter(is_processed=False)

        total = qs.count()
        self.stdout.write(f"Records to process: {total}")

        if total == 0:
            self.stdout.write(self.style.SUCCESS("Nothing to do."))
            return

        processed = 0
        errors = 0
        offset = 0

        while offset < total:
            batch = list(qs.order_by("pk")[offset: offset + batch_size])

            for report in batch:
                if dry_run:
                    self.stdout.write(
                        f"  [DRY RUN] Would normalise id={report.pk}: {report.title[:60]!r}"
                    )
                    processed += 1
                    continue

                try:
                    with transaction.atomic():
                        normalize_report(report)
                    processed += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  [{report.pk}] {report.severity.upper():8s} | "
                            f"{str(report.category or 'Uncategorised'):25s} | "
                            f"{report.title[:50]!r}"
                        )
                    )
                except Exception as exc:
                    errors += 1
                    logger.exception("Failed to normalise report id=%s", report.pk)
                    self.stderr.write(
                        self.style.ERROR(f"  Error on id={report.pk}: {exc}")
                    )

            offset += batch_size

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done — processed: {processed}, errors: {errors}, total: {total}"
            )
        )
