# Build from repository root:
#   docker build -f services/query/Dockerfile .
FROM python:3.14-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY services/query/pyproject.toml services/query/README.md ./
COPY services/query/src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

EXPOSE 8081
USER nobody
CMD ["hammrly-query"]
