import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swiftcourier.settings")

app = Celery("swiftcourier")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()
