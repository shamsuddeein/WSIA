"""
Celery application entry point for WSIA.

Usage:
    celery -A wsia worker --loglevel=info
    celery -A wsia beat --loglevel=info
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "wsia.settings")

app = Celery("wsia")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
