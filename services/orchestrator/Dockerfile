# Build from repository root:
#   docker build -f services/orchestrator/Dockerfile .
FROM python:3.14-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY services/orchestrator/pyproject.toml services/orchestrator/README.md ./
COPY services/orchestrator/src ./src
COPY services/orchestrator/alembic.ini services/orchestrator/alembic ./

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "alembic>=1.13.0" \
    && pip install --no-cache-dir . \
    && command -v alembic \
    && alembic --version

USER nobody
CMD ["hammrly-orchestrator"]
