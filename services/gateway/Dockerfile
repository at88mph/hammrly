# Build from repository root:
#   docker build -f services/gateway/Dockerfile .
FROM python:3.14-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY services/gateway/pyproject.toml services/gateway/README.md ./
COPY services/gateway/src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# Contract schema (default resolver breaks when the package is installed to site-packages)
COPY contracts /app/contracts
ENV HAMMRLY_CONTRACT_SCHEMA_PATH=/app/contracts/job-submission/v1/schema.json

EXPOSE 8080
USER nobody
CMD ["hammrly-gateway"]
