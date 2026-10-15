#!/bin/sh
# Container entrypoint for the single-service image.
#
# RUN_MIGRATIONS_ON_START=1 runs the (idempotent) seed here, before any worker starts.
# That is for hosts with no pre-deploy step, such as Render's free plan. MongoDB needs no
# schema migration: collections and indexes are created by the app at startup.
#
# On Cloud Run, leave it unset. Cloud Run starts a second container whenever traffic
# rises, and each one would run the seed again at the same moment — one wins the unique
# index and the rest crash. Run `python -m app.cli seed` as a Cloud Run Job instead, so it
# happens once, deliberately, and a failed seed never takes the running version down.
# DEPLOYMENT.md step 6 has the commands.
set -e

if [ "${RUN_MIGRATIONS_ON_START:-0}" = "1" ]; then
    python -m app.core.seed
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}" --proxy-headers --forwarded-allow-ips="*"
