"""Vercel serverless entrypoint: exposes the Django WSGI app as `app`."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swiftcourier.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

app = get_wsgi_application()
