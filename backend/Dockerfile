FROM ghcr.io/astral-sh/uv:0.13.1 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /srv/backend
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --group dev
COPY . .
RUN useradd --uid 10001 --create-home app && mkdir -p /srv/backend/source-objects && chown -R app:app /srv/backend
USER app
ENV PATH="/srv/backend/.venv/bin:$PATH"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
