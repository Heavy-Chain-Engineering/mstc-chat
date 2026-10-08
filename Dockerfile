# check=error=true
# The line above turns Docker's build checks into errors, so a secret-shaped ARG or ENV
# (SecretsUsedInArgOrEnv) fails the build instead of printing a warning (ADR-07).
#
# Three stages: Node builds the browser client, uv installs the locked Python packages, and the
# runtime stage holds only Python, those packages, backend/ and the built client. No stage takes
# a secret: Cloud Run passes CLASS_PASSWORD and SESSION_SECRET to the running container.
# Base images are pinned to exact versions; Dependabot's docker entry proposes updates.

FROM node:26.9.0-slim AS client
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
# Install scripts stay off, so a compromised dependency cannot run code during the build.
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.12.4 AS uv

FROM python:3.14.8-slim AS deps
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
# --no-build accepts prebuilt wheels only, so no package's build script runs here.
RUN uv sync --locked --no-dev --no-build --no-install-project

FROM python:3.14.8-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home app
WORKDIR /app
COPY --from=deps /app/.venv /app/.venv
COPY pyproject.toml uv.lock ./
COPY backend/ backend/
COPY --from=client /app/frontend/dist frontend/dist
USER 10001:10001
# Cloud Run sets PORT (8080 by default); the server listens on 0.0.0.0:$PORT (ADR-01).
EXPOSE 8080
# Cloud Run ignores HEALTHCHECK; this one serves `docker run` locally.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8080') + '/', timeout=2)"]
CMD ["python", "-m", "backend"]
