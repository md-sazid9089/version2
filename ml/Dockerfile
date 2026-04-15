# ============================================================
# GoliTransit ML Module — Dockerfile
# ============================================================
# Multi-stage build for the ML prediction microservice.
#
# Stage 1 (builder): Install scikit-learn, pandas, numpy, etc.
# Stage 2 (runtime): Copy venv + app code into slim image
#
# The ML service runs a lightweight FastAPI server on port 8001
# that loads trained models and serves edge traversal predictions.
#
# Usage:
#   docker build -t golitransit-ml ./ml
#   docker run -p 8001:8001 golitransit-ml
# ============================================================

# ─── Stage 1: Builder ───────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools needed for numpy/scikit-learn compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    gfortran \
    libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt


# ─── Stage 2: Runtime ───────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="GoliTransit Team"
LABEL description="GoliTransit ML Prediction Service — Edge traversal time predictions"

WORKDIR /app

# Install minimal runtime system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenblas0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set Python to run unbuffered
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy application code
COPY . .

# Ensure models and data directories exist
RUN mkdir -p /app/models /app/data

# Expose the ML prediction port
EXPOSE 8001

# Health check — hit the /health endpoint every 30s
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Default command
CMD ["python", "predict.py"]
