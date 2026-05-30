import django_filters

from reports.models import HackReport


class HackReportFilter(django_filters.FilterSet):
    category = django_filters.CharFilter(field_name="category__slug", lookup_expr="iexact")
    severity = django_filters.ChoiceFilter(choices=HackReport.Severity.choices)
    source = django_filters.CharFilter(lookup_expr="iexact")
    is_processed = django_filters.BooleanFilter()
    published_after = django_filters.DateTimeFilter(field_name="published_at", lookup_expr="gte")
    published_before = django_filters.DateTimeFilter(field_name="published_at", lookup_expr="lte")

    class Meta:
        model = HackReport
        fields = ["category", "severity", "source", "is_processed"]
