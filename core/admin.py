from django.contrib import admin

from .models import PipelineRun


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display = (
        "started_at",
        "status",
        "scraped_count",
        "new_count",
        "skipped_count",
        "error_count",
        "duration_display",
        "celery_task_id",
    )
    list_filter = ("status",)
    readonly_fields = (
        "started_at",
        "finished_at",
        "celery_task_id",
        "scraped_count",
        "new_count",
        "skipped_count",
        "error_count",
        "error_detail",
    )
    ordering = ("-started_at",)
    date_hierarchy = "started_at"

    @admin.display(description="Duration")
    def duration_display(self, obj):
        if obj.finished_at:
            secs = (obj.finished_at - obj.started_at).total_seconds()
            return f"{secs:.0f}s"
        return "—"
