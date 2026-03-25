# ── Stage 1: Build frontend ───────────────────────────────────────────────────
FROM oven/bun:1 AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile
COPY frontend/ .
RUN bun run build

# ── Stage 2: Python app ──────────────────────────────────────────────────────
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlcipher-dev \
    chromium \
    chromium-driver \
    tesseract-ocr \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy backend
COPY src/ src/

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist /app/static

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
