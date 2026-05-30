from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import HealthCheckView, HackReportViewSet, ReportSearchView

router = DefaultRouter()
router.register(r"reports", HackReportViewSet, basename="hackreport")

urlpatterns = [
    path("", include(router.urls)),
    path("search/", ReportSearchView.as_view(), name="report-search"),
    path("health/", HealthCheckView.as_view(), name="health-check"),
]
