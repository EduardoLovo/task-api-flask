# syntax=docker/dockerfile:1

# Imagem base configurável: docker build --build-arg PYTHON_IMAGE=python:3.14-slim-bookworm .
ARG PYTHON_IMAGE=python:3.14-slim

# ---- Etapa 1: instala as dependências com uv -------------------------------
FROM ${PYTHON_IMAGE} AS build

COPY --from=ghcr.io/astral-sh/uv:0.12.20 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependências primeiro: essa camada só é refeita quando o uv.lock muda.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY app ./app
COPY main.py ./

# ---- Etapa 2: imagem final, sem uv e sem ferramentas de build --------------
FROM ${PYTHON_IMAGE}

RUN useradd --create-home --uid 10001 appuser

WORKDIR /app
COPY --from=build /app /app

RUN mkdir -p /app/data && chown appuser:appuser /app/data

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    PORT=5000 \
    DATABASE_PATH=/app/data/database.sqlite

USER appuser
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=2)"]

CMD ["python", "main.py"]
