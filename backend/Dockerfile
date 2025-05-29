# Multi-stage build for optimized Python image
FROM python:3.12-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Create wheels
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

# Runtime stage
FROM python:3.12-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user FIRST
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Copy wheels and install
COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache /wheels/*

# CRITICAL: Create ALL directories with proper ownership BEFORE switching user
RUN mkdir -p /app/models/artifacts && \
    mkdir -p /app/logs && \
    mkdir -p /app/data && \
    mkdir -p /app/app && \
    mkdir -p /app/app/ml && \
    mkdir -p /app/app/ml/models && \
    mkdir -p /app/app/ml/training && \
    chmod -R 755 /app && \
    chown -R appuser:appuser /app

# Copy application code with correct ownership
COPY --chown=appuser:appuser . .

# Create volume mount points (optional, but ensures they exist)
VOLUME ["/app/models/artifacts", "/app/data", "/app/logs"]

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]