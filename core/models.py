"""
Core models.

Contains infrastructure-level models used across the project.
"""

from django.db import models
from django.utils import timezone


class PipelineRun(models.Model):
    """
    Audit log for every pipeline execution.

    One record is created at the start of each run and updated on completion.
    Provides visibility into pipeline health, duration, and record counts
    without needing to dig through logs.
    """

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        PARTIAL = "partial", "Partial (some errors)"
        FAILED = "failed", "Failed"

    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.RUNNING,
        db_index=True,
    )

    # Counters
    scraped_count = models.PositiveIntegerField(default=0, help_text="Articles returned by scraper")
    new_count = models.PositiveIntegerField(default=0, help_text="New records inserted")
    skipped_count = models.PositiveIntegerField(default=0, help_text="Duplicates skipped")
    error_count = models.PositiveIntegerField(default=0, help_text="Records that failed processing")

    # Optional structured error info
    error_detail = models.TextField(blank=True, default="")

    # Celery task ID for cross-referencing with broker
    celery_task_id = models.CharField(max_length=200, blank=True, db_index=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Pipeline Run"
        verbose_name_plural = "Pipeline Runs"

    def __str__(self):
        duration = ""
        if self.finished_at:
            secs = (self.finished_at - self.started_at).total_seconds()
            duration = f" ({secs:.0f}s)"
        return f"PipelineRun [{self.status}]{duration} @ {self.started_at:%Y-%m-%d %H:%M}"

    def mark_finished(self, status: str) -> None:
        self.status = status
        self.finished_at = timezone.now()
        self.save(update_fields=["status", "finished_at", "new_count", "skipped_count", "error_count"])
