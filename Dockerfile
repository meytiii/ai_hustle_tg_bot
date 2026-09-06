# Multi-stage lightweight Python Dockerfile
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final minimal production stage
FROM python:3.11-slim

WORKDIR /app

# Create non-root system user for security
RUN useradd -u 1001 -m botuser

# Copy installed wheels from builder
COPY --from=builder /root/.local /home/botuser/.local
ENV PATH=/home/botuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# Copy source code and assets
COPY --chown=botuser:botuser src/ ./src/
COPY --chown=botuser:botuser assets/ ./assets/

# Ensure persistent data directory exists and is owned by botuser
RUN mkdir -p /app/data && chown -R botuser:botuser /app/data

USER botuser

VOLUME ["/app/data"]

CMD ["python", "-m", "src.main"]
