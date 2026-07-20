# Build from repository root:
#   docker build -f services/catalog/Dockerfile .
FROM python:3.14-slim-bookworm

WORKDIR /app

COPY services/catalog/pyproject.toml services/catalog/README.md ./
COPY services/catalog/src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

EXPOSE 8082
USER nobody
CMD ["hammrly-catalog"]
