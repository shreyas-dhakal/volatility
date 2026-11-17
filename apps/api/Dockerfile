FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app/apps/api
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev
COPY apps/api/ ./
COPY examples/ /app/examples/
EXPOSE 8000
CMD ["sh", "-c", "uv run --frozen --no-dev alembic upgrade head && uv run --frozen --no-dev uvicorn galvanise.main:app --host 0.0.0.0 --port 8000"]
