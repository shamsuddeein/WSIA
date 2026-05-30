"""
API serializers — Phase 6.

Added: SearchResultSerializer with match context, StatsSerializer.
"""

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from reports.models import Category, HackReport, Tag


class CategorySerializer(serializers.ModelSerializer):
    report_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "report_count"]


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name"]


class HackReportSerializer(serializers.ModelSerializer):
    """Full detail serializer — used by /api/reports/{id}/"""

    category = CategorySerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    severity_display = serializers.CharField(source="get_severity_display", read_only=True)

    class Meta:
        model = HackReport
        fields = [
            "id",
            "title",
            "description",
            "source_url",
            "source",
            "severity",
            "severity_display",
            "category",
            "tags",
            "is_processed",
            "ai_summary",
            "published_at",
            "created_at",
        ]


class HackReportListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views — no description or raw_data."""

    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    category_slug = serializers.CharField(source="category.slug", read_only=True, default=None)
    severity_display = serializers.CharField(source="get_severity_display", read_only=True)
    tag_names = serializers.SerializerMethodField()

    class Meta:
        model = HackReport
        fields = [
            "id",
            "title",
            "source",
            "source_url",
            "severity",
            "severity_display",
            "category_name",
            "category_slug",
            "tag_names",
            "is_processed",
            "published_at",
            "created_at",
        ]

    def get_tag_names(self, obj) -> list[str]:
        return list(obj.tags.values_list("name", flat=True))


class SearchResultSerializer(HackReportListSerializer):
    """
    Extends list serializer with a short description excerpt for search results.
    Truncates to 300 chars so clients get context without the full body.
    """

    excerpt = serializers.SerializerMethodField()

    class Meta(HackReportListSerializer.Meta):
        fields = HackReportListSerializer.Meta.fields + ["excerpt"]

    def get_excerpt(self, obj):
        text = obj.description or ""
        if len(text) <= 300:
            return text
        return text[:297] + "…"
    def get_excerpt(self, obj) -> str:
        text = obj.description or ""
        if len(text) <= 300:
            return text
        return text[:297] + "…"


class CategoryStatsSerializer(serializers.Serializer):
    """Used by the /api/stats/ endpoint."""

    name = serializers.CharField()
    slug = serializers.CharField()
    count = serializers.IntegerField()


class HealthSerializer(serializers.Serializer):
    """Serializer for the /api/health/ liveness probe."""

    status = serializers.CharField()
    db = serializers.CharField()


class StatsSerializer(serializers.Serializer):
    """Aggregate stats for the /api/stats/ endpoint."""

    total_reports = serializers.IntegerField()
    processed_reports = serializers.IntegerField()
    unprocessed_reports = serializers.IntegerField()
    by_severity = serializers.DictField(child=serializers.IntegerField())
    by_source = serializers.DictField(child=serializers.IntegerField())
    top_categories = CategoryStatsSerializer(many=True)
