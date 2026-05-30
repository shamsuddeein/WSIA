"""
API filters — Phase 6.

Comprehensive filtering for HackReport list and search views.
"""

import django_filters
from django.db.models import Q

from reports.models import HackReport


class HackReportFilter(django_filters.FilterSet):
    """
    FilterSet for /api/reports/.

    Supported params:
        category          — category slug (case-insensitive)
        severity          — low | medium | high | critical
        source            — exact source name (case-insensitive)
        is_processed      — true | false
        published_after   — ISO 8601 datetime (gte)
        published_before  — ISO 8601 datetime (lte)
        created_after     — ISO 8601 datetime (gte)
        created_before    — ISO 8601 datetime (lte)
        tag               — tag name (case-insensitive, any match)
        q                 — keyword search on title + description
    """

    category = django_filters.CharFilter(
        field_name="category__slug",
        lookup_expr="iexact",
        label="Category slug",
    )
    severity = django_filters.ChoiceFilter(
        choices=HackReport.Severity.choices,
        label="Severity level",
    )
    source = django_filters.CharFilter(
        lookup_expr="iexact",
        label="Source name",
    )
    is_processed = django_filters.BooleanFilter(
        label="Processing complete",
    )

    # Date range filters
    published_after = django_filters.IsoDateTimeFilter(
        field_name="published_at",
        lookup_expr="gte",
        label="Published on or after (ISO 8601)",
    )
    published_before = django_filters.IsoDateTimeFilter(
        field_name="published_at",
        lookup_expr="lte",
        label="Published on or before (ISO 8601)",
    )
    created_after = django_filters.IsoDateTimeFilter(
        field_name="created_at",
        lookup_expr="gte",
        label="Scraped on or after (ISO 8601)",
    )
    created_before = django_filters.IsoDateTimeFilter(
        field_name="created_at",
        lookup_expr="lte",
        label="Scraped on or before (ISO 8601)",
    )

    # Tag filter — match any report that has a tag with this name
    tag = django_filters.CharFilter(
        field_name="tags__name",
        lookup_expr="iexact",
        label="Tag name",
    )

    # Inline keyword search (also available as dedicated /api/search/ endpoint)
    q = django_filters.CharFilter(
        method="filter_keyword",
        label="Keyword search (title + description)",
    )

    class Meta:
        model = HackReport
        fields = [
            "category", "severity", "source", "is_processed",
            "published_after", "published_before",
            "created_after", "created_before",
            "tag", "q",
        ]

    def filter_keyword(self, queryset, name, value):  # noqa: ARG002
        if not value:
            return queryset
        return queryset.filter(
            Q(title__icontains=value) | Q(description__icontains=value)
        )
