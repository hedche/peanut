FROM python:3.12-alpine AS builder

# eMudhra intermediate CA compromise (2026-10-20): the base image's
# ca-certificates package predates the fixed Alpine build (20261020-r0),
# so pull the upgrade explicitly rather than relying on the base image.
RUN apk update && apk upgrade ca-certificates ca-certificates-bundle

# Install build dependencies only in builder stage
RUN apk add --no-cache gcc musl-dev linux-headers

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app/ app/
RUN uv sync --frozen --no-dev

# -----------------------------------------------------------
FROM python:3.12-alpine

# eMudhra intermediate CA compromise (2026-10-20): same ca-certificates
# upgrade in the runtime stage, which actually makes outbound TLS calls.
RUN apk update && apk upgrade ca-certificates ca-certificates-bundle

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY app/ app/

# Remove compiled Python cache files to save space
RUN find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true && \
    find /app -name "*.pyc" -delete 2>/dev/null || true

ARG GIT_SHA=unknown
ENV APP_VERSION=$GIT_SHA
ENV PATH="/app/.venv/bin:$PATH"

RUN mkdir -p /data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
