#!/bin/sh
# Container entrypoint for the single-service image.
#
# Render's free plan has no pre-deploy step, so RUN_MIGRATIONS_ON_START=1 runs the
# migrations and the (idempotent) seed here, once, before any worker starts. On a paid plan
# leave it unset and let `preDeployCommand` do it, so a failed migration never takes the
# running version down.
set -e

if [ "${RUN_MIGRATIONS_ON_START:-0}" = "1" ]; then
    alembic upgrade head
    python -m app.core.seed
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}" --proxy-headers --forwarded-allow-ips="*"
