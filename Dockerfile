# ─────────────────────────────────────────────────────────────────────────────
# A1 Mail Dynamics — Production Docker Image
#
# Build:   docker build -t a1maildynamics .
# Run:     docker run -p 5000:5000 --env-file .env a1maildynamics
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Build the React frontend ─────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /build/client
COPY client/package*.json ./
RUN npm ci --silent
COPY client/ ./
RUN npm run build


# ── Stage 2: Python production image ──────────────────────────────────────────
FROM python:3.12-slim

LABEL org.opencontainers.image.title="A1 Mail Dynamics" \
      org.opencontainers.image.description="AI Marketing Automation — Production Server" \
      org.opencontainers.image.vendor="A1 Technovation"

# System deps needed by Playwright and Pillow (icon generation not needed in prod)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps before copying source so Docker cache layer is reused.
# requirements-web.txt excludes desktop-only packages (pywebview, pythonnet,
# clr_loader) that are not needed in server mode and fail on Linux.
COPY requirements-web.txt ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements-web.txt

# Copy source (excluding heavy dev artefacts via .dockerignore)
COPY app/ ./app/
COPY data/sample_contacts.csv ./data/sample_contacts.csv
COPY .env.example ./

# Pull compiled frontend from the builder stage
COPY --from=frontend-builder /build/client/dist ./client/dist

# Writable runtime dirs
RUN mkdir -p data/runtime data/attachments logs \
 && chmod 777 data/runtime data/attachments logs

# Security: run as non-root
RUN useradd --no-create-home --system a1app \
 && chown -R a1app:a1app /app
USER a1app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production \
    HOST=0.0.0.0 \
    PORT=5000 \
    WAITRESS_THREADS=8

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

CMD ["python", "-m", "app.main"]
