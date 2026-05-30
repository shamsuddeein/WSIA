from django.contrib import admin

from .models import Category, HackReport, Tag


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(HackReport)
class HackReportAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "source",
        "severity",
        "category",
        "is_processed",
        "published_at",
        "created_at",
    )
    list_filter = ("severity", "is_processed", "source", "category")
    search_fields = ("title", "description", "source_url")
    readonly_fields = ("hash", "created_at", "raw_data")
    filter_horizontal = ("tags",)
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
