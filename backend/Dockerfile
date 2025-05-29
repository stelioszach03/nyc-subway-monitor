FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 appuser

WORKDIR /app

COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache /wheels/*

# Create directories with proper permissions
RUN mkdir -p /app/models/artifacts /app/logs /app/data && \
    chown -R appuser:appuser /app

COPY --chown=appuser:appuser . .

# Download GTFS data
RUN python scripts/download_gtfs_static.py || true

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]