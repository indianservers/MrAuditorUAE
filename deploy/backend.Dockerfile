FROM node:22-bookworm-slim AS ml
WORKDIR /srv/ml-engine
COPY ml-engine/package.json ml-engine/package-lock.json ./
RUN npm ci
COPY ml-engine/ ./
RUN npm run build && npm prune --omit=dev

FROM ghcr.io/astral-sh/uv:0.13.1 AS uv
FROM python:3.12-slim-trixie AS runtime-build
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


# Candidate target: default runtime remains unchanged until CI qualifies it.
FROM runtime-build AS minimal-assets
USER root
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends libbz2-1.0 libexpat1 libffi8 libgcc-s1 libgomp1 liblzma5 libsqlite3-0 libssl3t64 libstdc++6 libzstd1 zlib1g && rm -rf /var/lib/apt/lists/*
COPY deploy/runtime_bundle.py /tmp/runtime_bundle.py
RUN /srv/backend/.venv/bin/python /tmp/runtime_bundle.py

FROM gcr.io/distroless/cc-debian13@sha256:d74d144baa124dd9defd01d71872bb56c49d4441dba6153ccf790364f97e64b1 AS minimal-runtime
COPY --from=minimal-assets /runtime-python/usr/local/ /usr/local/
COPY --from=minimal-assets /runtime-libs/ /
COPY --from=runtime-build --chown=10001:10001 /srv/ /srv/
COPY --from=runtime-build /etc/passwd /etc/passwd
COPY --from=runtime-build /etc/group /etc/group
COPY --from=runtime-build --chown=10001:10001 /home/app/ /home/app/
COPY deploy/runtime_smoke.py /srv/backend/runtime_smoke.py
WORKDIR /srv/backend
USER 10001:10001
ENV PATH="/srv/backend/.venv/bin:/usr/local/bin:/usr/bin:/bin" LD_LIBRARY_PATH="/usr/local/lib" HOME="/home/app" PYTHONDONTWRITEBYTECODE="1"
HEALTHCHECK --interval=30s --timeout=10s --retries=3 CMD ["python","-c","import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready')"]
CMD ["/srv/backend/.venv/bin/uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--no-access-log"]

FROM runtime-build AS runtime
