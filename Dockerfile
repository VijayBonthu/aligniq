# syntax=docker/dockerfile:1.6
# ---- builder ----
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

# Build deps for native wheels (lxml, psycopg2, pillow, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libpq-dev \
        libffi-dev \
        libxml2-dev \
        libxslt1-dev \
        libjpeg-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

# Strip pyc cache files and tests bundled inside site-packages. Saves ~200MB
# without breaking anything at runtime.
RUN find /install -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true \
    && find /install -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true \
    && find /install -type f -name "*.pyc" -delete

# ---- runtime ----
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# Runtime system deps. ghostscript is required by camelot's lattice backend.
# poppler-utils stays for pdfplumber/pypdfium2 fallbacks. libgl1, libglib,
# tesseract are gone with easyocr/opencv.
RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils \
        ghostscript \
        libpq5 \
        libmagic1 \
        libglib2.0-0 \
        libgl1 \
        curl \
        unzip \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# AWS CLI v2 — entrypoint uses it to pull SSM SecureString params.
RUN curl -sSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscli.zip \
    && unzip -q /tmp/awscli.zip -d /tmp \
    && /tmp/aws/install \
    && rm -rf /tmp/awscli.zip /tmp/aws

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app
COPY src ./src
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# Run as non-root
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

EXPOSE 8080
ENTRYPOINT ["./entrypoint.sh"]
# --workers 1 until auth_states moves out of process memory into Redis.
# OAuth state lookup must hit the same worker that set it, so multi-worker
# breaks login intermittently. asyncio still gives us concurrency for
# I/O-bound work (pipeline awaits OpenAI ~90% of the time).
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
