# Gate / farm monitor server: FastAPI + built React dashboard.
# Builds on amd64 and arm64 (Raspberry Pi 4/5) — no Node needed on the host.

# ---- frontend -------------------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- server ---------------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install . && useradd --system --uid 10001 --home /app gatemonitor \
    && mkdir -p /data && chown gatemonitor /data
COPY --from=frontend /build/dist /app/frontend/dist

ENV HOST=0.0.0.0 \
    PORT=8000 \
    FRONTEND_DIST=/app/frontend/dist \
    DB_PATH=/data/gate_monitor.db
VOLUME ["/data"]
EXPOSE 8000
USER gatemonitor
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health', timeout=4)"
CMD ["gate-monitor"]
