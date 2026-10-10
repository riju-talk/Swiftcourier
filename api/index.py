"""Vercel serverless entrypoint: exposes the Django WSGI app as `app`.

DEMO DIAGNOSTICS: if Django fails to boot (or a request raises past Django),
return the traceback as plain text instead of Vercel's opaque
FUNCTION_INVOCATION_FAILED. Remove _report() before production.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swiftcourier.settings")


def _report(exc_text):
    print(exc_text, file=sys.stderr, flush=True)
    body = ("SwiftCourier failed to start/serve:\n\n" + exc_text).encode()

    def _app(environ, start_response):
        start_response(
            "500 Internal Server Error",
            [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(body)))],
        )
        return [body]

    return _app


try:
    from django.core.wsgi import get_wsgi_application

    _django = get_wsgi_application()

    def app(environ, start_response):
        try:
            return _django(environ, start_response)
        except Exception:
            return _report(traceback.format_exc())(environ, start_response)

except Exception:
    app = _report(traceback.format_exc())
