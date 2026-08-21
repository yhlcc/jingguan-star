FROM node:24-alpine AS frontend-builder

ARG NPM_REGISTRY=https://registry.npmmirror.com

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm config set registry "$NPM_REGISTRY" && npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim

ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

ENV HOST=0.0.0.0 \
    PORT=8000 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin appuser

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt -i "$PIP_INDEX_URL"

COPY --chown=appuser:appuser . .
COPY --from=frontend-builder --chown=appuser:appuser /build/frontend/dist /app/frontend/dist

RUN mkdir -p /app/data /app/seed \
    && cp /app/data/jingguan_star.db /app/seed/jingguan_star.db \
    && rm /app/data/jingguan_star.db \
    && chown -R appuser:appuser /app/data /app/seed

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/api/health', timeout=3).read(1)"

CMD ["python", "run.py"]
