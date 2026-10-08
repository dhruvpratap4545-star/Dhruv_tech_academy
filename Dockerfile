# Single-service image: the API also serves the built web app, so the platform runs on one
# URL (see backend/app/core/spa.py). Build from the repo root:
#   docker build -t dhruv .
# backend/Dockerfile stays as the API-only image.

# --- Stage 1: build the frontend --------------------------------------------------------
FROM node:24-slim AS web
WORKDIR /web

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# Relative: the browser calls the API on the same origin, whatever the host name is.
ENV VITE_API_URL=/api/v1
RUN npm run build

# --- Stage 2: the API, carrying the built frontend --------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FRONTEND_DIST_DIR=/app/web

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY --from=web /web/dist ./web

RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD curl -fsS "http://localhost:${PORT:-8000}/healthz" || exit 1

# Render injects PORT. The script also runs migrations when RUN_MIGRATIONS_ON_START=1.
CMD ["sh", "scripts/start.sh"]
