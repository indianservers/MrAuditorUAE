FROM node:22-bookworm-slim AS ml
WORKDIR /srv/ml-engine
COPY ml-engine/package.json ml-engine/package-lock.json ./
RUN npm ci
COPY ml-engine/ ./
RUN npm run build && npm prune --omit=dev

FROM ghcr.io/astral-sh/uv:0.13.1 AS uv
FROM python:3.12-slim-trixie
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends libstdc++6 libatomic1 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
COPY --from=ml /usr/local/bin/node /usr/local/bin/node
RUN node --version
COPY --from=ml /srv/ml-engine /srv/ml-engine
WORKDIR /srv/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev && .venv/bin/python -c "from PIL import Image; import pypdf, pypdfium2, onnxruntime, rapidocr, fpdf, uharfbuzz; image = Image.new('RGB', (2, 2)); image.close()"
COPY backend/app/ ./app/
COPY backend/alembic/ ./alembic/
COPY backend/alembic.ini ./alembic.ini
RUN useradd --uid 10001 --create-home app && chown -R app:app /srv/backend /srv/ml-engine
USER app
ENV PATH="/srv/backend/.venv/bin:$PATH"
HEALTHCHECK --interval=30s --timeout=10s --retries=3 CMD ["python","-c","import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready')"]
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--no-access-log"]
