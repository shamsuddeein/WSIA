from rest_framework import serializers

from reports.models import Category, HackReport, Tag


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug"]


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name"]


class HackReportSerializer(serializers.ModelSerializer):
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
    """Lighter serializer for list views — omits description and raw_data."""

    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    severity_display = serializers.CharField(source="get_severity_display", read_only=True)

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
            "is_processed",
            "published_at",
            "created_at",
        ]
