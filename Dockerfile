FROM python:3.12-alpine AS builder

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

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY app/ app/

# Remove compiled Python cache files to save space
RUN find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true && \
    find /app -name "*.pyc" -delete 2>/dev/null || true

ENV PATH="/app/.venv/bin:$PATH"

RUN mkdir -p /data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
