import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "idiotship.settings")

app = Celery("idiotship")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()
