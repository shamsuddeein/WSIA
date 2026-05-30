from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CategoryListView,
    HealthCheckView,
    HackReportViewSet,
    ReportSearchView,
    StatsView,
)

router = DefaultRouter()
router.register(r"reports", HackReportViewSet, basename="hackreport")

urlpatterns = [
    path("", include(router.urls)),
    path("search/",     ReportSearchView.as_view(), name="report-search"),
    path("stats/",      StatsView.as_view(),        name="report-stats"),
    path("categories/", CategoryListView.as_view(),  name="category-list"),
    path("health/",     HealthCheckView.as_view(),   name="health-check"),
]
