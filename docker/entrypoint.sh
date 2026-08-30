#!/usr/bin/env bash
set -euo pipefail

# Wait for Postgres + Redis before starting.
python - <<'PY'
import os, time, socket, sys

def wait(host, port, name):
    for _ in range(60):
        try:
            socket.create_connection((host, int(port)), timeout=2).close()
            print(f"  {name} up ({host}:{port})", flush=True)
            return
        except OSError:
            time.sleep(1)
    sys.exit(f"  timed out waiting for {name} ({host}:{port})")

wait(os.getenv("DATABASE_HOST", "db"), os.getenv("DATABASE_PORT", "5432"), "postgres")
redis = os.getenv("REDIS_URL", "redis://redis:6379")
hostport = redis.split("://", 1)[-1].split("/")[0]
host, _, port = hostport.partition(":")
wait(host, port or "6379", "redis")
PY

case "${1:-web}" in
  web)
    python manage.py migrate --no-input
    if [ "${SEED_DEMO_USERS:-0}" = "1" ]; then
        python manage.py seed_demo_users || true
    fi
    exec gunicorn swiftcourier.wsgi:application \
        --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-3}" \
        --timeout 60 --access-logfile - --error-logfile -
    ;;
  worker)
    exec celery -A swiftcourier worker -l info \
        -Q "${2:-default,ship,webhooks}" \
        --concurrency "${CELERY_WORKER_CONCURRENCY:-2}" \
        -n "${2:-all}@%h"
    ;;
  beat)
    exec celery -A swiftcourier beat -l info \
        --scheduler django_celery_beat.schedulers:DatabaseScheduler
    ;;
  crontab)
    python manage.py crontab add && python manage.py crontab show
    ;;
  *)
    exec "$@"
    ;;
esac
