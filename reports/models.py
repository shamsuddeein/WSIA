import logging

from django.db import models
from django.utils.text import slugify
from pgvector.django import VectorField

logger = logging.getLogger(__name__)


class Category(models.Model):
    """High-level exploit category, e.g. Reentrancy, Flash Loan."""

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Tag(models.Model):
    """Short label for cross-cutting concerns, e.g. 'defi', 'bridge'."""

    name = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class HackReport(models.Model):
    """Central model — one record per security incident."""

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    # Core fields
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    source_url = models.URLField(max_length=2000)
    source = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Provider name, e.g. rekt.news",
    )

    # Classification
    severity = models.CharField(
        max_length=20,
        choices=Severity.choices,
        default=Severity.MEDIUM,
        db_index=True,
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="reports")

    # Pipeline state
    is_processed = models.BooleanField(
        default=False,
        db_index=True,
        help_text="False until analytics has cleaned this record.",
    )

    # Deduplication — SHA-256 of source_url
    hash = models.CharField(max_length=64, unique=True, db_index=True)

    # Raw source payload — store anything that doesn't map to the schema
    raw_data = models.JSONField(default=dict, blank=True)

    # AI layer — added in Phase 7 migration
    ai_summary = models.TextField(null=True, blank=True)
    embedding = VectorField(dimensions=1536, null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    published_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Original publication date from the source.",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["title"]),
            models.Index(fields=["severity"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["published_at"]),
            models.Index(fields=["source"]),
            # hash is already indexed via unique=True
        ]

    def __str__(self):
        return f"[{self.get_severity_display()}] {self.title}"
