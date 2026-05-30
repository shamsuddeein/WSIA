"""
API views — Phase 6.

Endpoints:
    GET  /api/reports/              HackReport list (paginated, filtered)
    GET  /api/reports/{id}/         HackReport detail
    GET  /api/search/?q=...         Full-text keyword search
    GET  /api/stats/                Aggregate counts
    GET  /api/categories/           Category list with report counts
    GET  /api/health/               Liveness probe
"""

import logging

from django.db.models import Case, Count, IntegerField, Q, Value, When
from rest_framework import generics, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
import numpy as np

from reports.models import Category, HackReport

from .filters import HackReportFilter
from .serializers import (
    CategorySerializer,
    HackReportListSerializer,
    HackReportSerializer,
    SearchResultSerializer,
    StatsSerializer,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity ordering map — critical=0 (highest), low=3 (lowest)
# Used for consistent numeric ordering of a CharField.
# ---------------------------------------------------------------------------

SEVERITY_ORDER = Case(
    When(severity="critical", then=Value(0)),
    When(severity="high",     then=Value(1)),
    When(severity="medium",   then=Value(2)),
    When(severity="low",      then=Value(3)),
    default=Value(99),
    output_field=IntegerField(),
)

_ALLOWED_ORDERINGS = {
    "created_at":    "created_at",
    "-created_at":   "-created_at",
    "published_at":  "published_at",
    "-published_at": "-published_at",
    # severity_order: 0=critical (highest) … 3=low (lowest)
    # "-severity" → most severe first → ascending severity_order (0,1,2,3)
    # "severity"  → least severe first → descending severity_order (3,2,1,0)
    "-severity":     "severity_order",
    "severity":      "-severity_order",
    "title":         "title",
    "-title":        "-title",
}


def _apply_ordering(qs, ordering_param: str, default="-created_at"):
    """Resolve an ordering param to a safe DB field and apply it."""
    db_field = _ALLOWED_ORDERINGS.get(ordering_param, default)
    if "severity_order" in db_field:
        qs = qs.annotate(severity_order=SEVERITY_ORDER)
    return qs.order_by(db_field)


# ---------------------------------------------------------------------------
# /api/reports/  and  /api/reports/{id}/
# ---------------------------------------------------------------------------

class HackReportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List and retrieve HackReport records.

    Filtering params (all optional, combinable):
        q               — keyword search on title + description
        category        — category slug (case-insensitive)
        severity        — low | medium | high | critical
        source          — source name (case-insensitive)
        is_processed    — true | false
        tag             — tag name (case-insensitive)
        published_after — ISO 8601 datetime
        published_before— ISO 8601 datetime
        created_after   — ISO 8601 datetime
        created_before  — ISO 8601 datetime
        ordering        — created_at | -created_at | published_at | -published_at
                          severity | -severity | title | -title
    """

    filterset_class = HackReportFilter

    def get_queryset(self):
        ordering = self.request.query_params.get("ordering", "-created_at")
        # Annotate first so severity_order is available before any filter/distinct
        qs = (
            HackReport.objects
            .annotate(severity_order=SEVERITY_ORDER)
            .select_related("category")
            .prefetch_related("tags")
        )
        db_field = _ALLOWED_ORDERINGS.get(ordering, "-created_at")
        return qs.order_by(db_field)

    def get_serializer_class(self):
        if self.action == "list":
            return HackReportListSerializer
        return HackReportSerializer

    @action(detail=True, methods=['get'])
    def similar(self, request, pk=None):
        report = self.get_object()
        if not report.embedding:
            return Response({"error": "No embedding generated for this report yet."}, status=404)
            
        target_vec = np.array(report.embedding)
        qs = HackReport.objects.filter(
            is_processed=True
        ).exclude(pk=report.pk).exclude(embedding__isnull=True).select_related("category").prefetch_related("tags")
        
        results = []
        for other in qs:
            other_vec = np.array(other.embedding)
            sim = np.dot(target_vec, other_vec) / (np.linalg.norm(target_vec) * np.linalg.norm(other_vec))
            results.append((sim, other))
            
        results.sort(key=lambda x: x[0], reverse=True)
        top_5 = [r[1] for r in results[:5]]
        
        serializer = HackReportListSerializer(top_5, many=True)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# /api/search/
# ---------------------------------------------------------------------------

class ReportSearchView(generics.ListAPIView):
    """
    Full-text keyword search across title and description of processed reports.

    Query params:
        q               — search term (searches title + description)
        category        — filter by category slug
        severity        — filter by severity
        source          — filter by source
        tag             — filter by tag name
        published_after — ISO 8601 datetime
        published_before— ISO 8601 datetime
        ordering        — field to order by (default: -created_at)
    """

    serializer_class = SearchResultSerializer

    def get_queryset(self):
        params = self.request.query_params
        q = params.get("q", "").strip()

        qs = (
            HackReport.objects
            .filter(is_processed=True)
            .select_related("category")
            .prefetch_related("tags")
        )

        # Keyword search
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

        # Additional filters
        category = params.get("category", "").strip()
        if category:
            qs = qs.filter(category__slug__iexact=category)

        severity = params.get("severity", "").strip()
        if severity and severity in HackReport.Severity.values:
            qs = qs.filter(severity=severity)

        source = params.get("source", "").strip()
        if source:
            qs = qs.filter(source__iexact=source)

        tag = params.get("tag", "").strip()
        if tag:
            qs = qs.filter(tags__name__iexact=tag)

        published_after = params.get("published_after", "").strip()
        if published_after:
            qs = qs.filter(published_at__gte=published_after)

        published_before = params.get("published_before", "").strip()
        if published_before:
            qs = qs.filter(published_at__lte=published_before)

        ordering = params.get("ordering", "-created_at")
        # Annotate severity_order before distinct to avoid SQLite ordering issues
        qs = qs.annotate(severity_order=SEVERITY_ORDER)
        db_field = _ALLOWED_ORDERINGS.get(ordering, "-created_at")
        return qs.order_by(db_field).distinct()


# ---------------------------------------------------------------------------
# /api/stats/
# ---------------------------------------------------------------------------

class StatsView(APIView):
    """
    Aggregate statistics for the full dataset.

    Returns:
        total_reports       — all HackReport records
        processed_reports   — is_processed=True
        unprocessed_reports — is_processed=False
        by_severity         — count per severity level
        by_source           — count per source name
        top_categories      — top 10 categories by report count
    """

    def get(self, request):
        qs = HackReport.objects.all()

        total = qs.count()
        processed = qs.filter(is_processed=True).count()

        # Counts per severity
        by_severity = {}
        for sev in HackReport.Severity.values:
            by_severity[sev] = qs.filter(severity=sev).count()

        # Counts per source
        by_source = {}
        for row in qs.values("source").annotate(n=Count("id")).order_by("-n"):
            by_source[row["source"]] = row["n"]

        # Top 10 categories
        top_categories = (
            Category.objects
            .annotate(report_count=Count("reports"))
            .filter(report_count__gt=0)
            .order_by("-report_count")[:10]
        )
        top_cats_data = [
            {"name": c.name, "slug": c.slug, "count": c.report_count}
            for c in top_categories
        ]

        data = {
            "total_reports": total,
            "processed_reports": processed,
            "unprocessed_reports": total - processed,
            "by_severity": by_severity,
            "by_source": by_source,
            "top_categories": top_cats_data,
        }
        serializer = StatsSerializer(data)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# /api/categories/
# ---------------------------------------------------------------------------

class CategoryListView(generics.ListAPIView):
    """
    List all categories with their report counts, ordered by count descending.
    """

    serializer_class = CategorySerializer

    def get_queryset(self):
        return (
            Category.objects
            .annotate(report_count=Count("reports"))
            .order_by("-report_count", "name")
        )


# ---------------------------------------------------------------------------
# /api/health/
# ---------------------------------------------------------------------------

class HealthCheckView(APIView):
    """Liveness probe — returns 200 if Django + DB are reachable."""

    def get(self, request):
        # Touch the DB to confirm connectivity
        try:
            HackReport.objects.exists()
            db_ok = True
        except Exception:
            db_ok = False

        return Response({
            "status": "ok" if db_ok else "degraded",
            "db": "ok" if db_ok else "error",
        }, status=200 if db_ok else 503)
