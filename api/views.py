import logging

from django.db.models import Q
from rest_framework import generics, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.models import HackReport

from .filters import HackReportFilter
from .serializers import HackReportListSerializer, HackReportSerializer

logger = logging.getLogger(__name__)


class HackReportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List and retrieve HackReport records.

    Supports filtering by: category, severity, source, is_processed,
    published_after, published_before.
    """

    queryset = HackReport.objects.select_related("category").prefetch_related("tags").order_by("-created_at")
    filterset_class = HackReportFilter

    def get_serializer_class(self):
        if self.action == "list":
            return HackReportListSerializer
        return HackReportSerializer


class ReportSearchView(generics.ListAPIView):
    """
    Full-text keyword search across title and description.

    Query params:
        q          — search term (required)
        category   — filter by category slug
        severity   — filter by severity
        ordering   — field to order by (default: -created_at)
    """

    serializer_class = HackReportListSerializer

    def get_queryset(self):
        params = self.request.query_params
        q = params.get("q", "").strip()

        qs = HackReport.objects.filter(is_processed=True).select_related("category")

        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

        category = params.get("category", "").strip()
        if category:
            qs = qs.filter(category__slug__iexact=category)

        severity = params.get("severity", "").strip()
        if severity:
            qs = qs.filter(severity=severity)

        ordering = params.get("ordering", "-created_at")
        allowed_orderings = {
            "created_at", "-created_at",
            "published_at", "-published_at",
            "severity", "-severity",
        }
        if ordering not in allowed_orderings:
            ordering = "-created_at"

        return qs.order_by(ordering)


class HealthCheckView(APIView):
    """Simple liveness probe — returns 200 if Django is up."""

    def get(self, request):
        return Response({"status": "ok"})
