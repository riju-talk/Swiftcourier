# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# System libs: psycopg2 build (libpq), WeasyPrint PDF stack (cairo/pango/gdk),
# curl for healthchecks.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl \
        libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
        libffi-dev shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Dependencies first (cached layer). The vendored PhonePe SDK is a path dep in
# pyproject.toml, so it has to be present before `uv sync`.
COPY pyproject.toml uv.lock ./
COPY dev/phonepe_sdk-2.1.5.zip dev/phonepe_sdk-2.1.5.zip
RUN uv sync --frozen --no-install-project --no-dev

# App code
COPY . .
RUN uv sync --frozen --no-dev

# collectstatic at build time (whitenoise serves from static_prod/)
RUN DATABASE_ENGINE=django.db.backends.sqlite3 SECRET_KEY=build-only \
    python manage.py collectstatic --no-input --clear

RUN chmod +x docker/entrypoint.sh
ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["web"]
