# API-only image, deployed to Cloud Run as `dhruv-api`. Build context is backend/:
#   docker build -t dhruv-api backend
# The web app is a separate service (frontend/Dockerfile) that proxies /api/* here, so the
# browser sees one origin.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Every dependency ships a manylinux wheel for 3.12, so no compiler or libpq is needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

# Cloud Run injects PORT (the service's container port). The script runs the seed first
# when RUN_MIGRATIONS_ON_START=1.
EXPOSE 8080
CMD ["sh", "scripts/start.sh"]
