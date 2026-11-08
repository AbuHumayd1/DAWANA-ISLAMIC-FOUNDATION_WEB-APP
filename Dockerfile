# Zero-argument managed builds use approved Debian Bookworm tags.
# Release CI overrides these with resolved digests and a source revision.
# No registry publication is performed by this file.
ARG NODE_IMAGE=node:22.19.0-bookworm-slim
ARG PYTHON_IMAGE=python:3.13-slim-bookworm
FROM ${NODE_IMAGE} AS frontend
ARG NODE_IMAGE
WORKDIR /build
RUN case "$NODE_IMAGE" in node:22.19.0-bookworm-slim|*@sha256:*) ;; *) echo 'Approved Node image required.' >&2; exit 1 ;; esac \
    && node -e "if (process.versions.node.split('.')[0] !== '22') process.exit(1)"
COPY dawana-platform/package.json dawana-platform/package-lock.json ./
RUN npm ci
COPY dawana-platform/index.html dawana-platform/vite.config.js ./
COPY dawana-platform/src ./src
COPY dawana-platform/public ./public
ENV VITE_API_BASE_URL=/api/v1
RUN npm run build

FROM ${PYTHON_IMAGE} AS python-build
ARG PYTHON_IMAGE
WORKDIR /build
RUN case "$PYTHON_IMAGE" in python:3.13-slim-bookworm|*@sha256:*) ;; *) echo 'Approved Python image required.' >&2; exit 1 ;; esac
COPY backend/requirements.txt backend/constraints-staging.txt ./
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir \
    -r requirements.txt -c constraints-staging.txt && /opt/venv/bin/pip check \
    && /opt/venv/bin/pip freeze > /opt/venv/resolved-requirements.txt

FROM ${PYTHON_IMAGE} AS runtime
ARG SOURCE_REVISION=unversioned
LABEL org.opencontainers.image.revision=${SOURCE_REVISION}
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    DJANGO_SETTINGS_MODULE=config.settings.production DJANGO_DEPLOYMENT_TARGET=self-managed \
    DJANGO_BIND_ADDRESS=127.0.0.1 DJANGO_BIND_PORT=10000 PORT=8080
RUN (test "$SOURCE_REVISION" = unversioned || (test "${#SOURCE_REVISION}" -eq 40 && test -z "$(printf '%s' "$SOURCE_REVISION" | tr -d '0-9a-f')")) \
    && apt-get update && apt-get install -y --no-install-recommends \
    nginx supervisor tini fonts-liberation ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 dawana && useradd --uid 10001 --gid 10001 --no-create-home dawana \
    && mkdir -p /run/dawana /app/backend /app/dawana-platform/public /app/frontend
COPY --from=python-build /opt/venv /opt/venv
COPY backend /app/backend
COPY dawana-platform/public /app/dawana-platform/public
COPY --from=frontend /build/dist /app/frontend
COPY ops/container /app/container
WORKDIR /app/backend
# Collect static assets without production settings, secrets, Django model setup
# or a database. The manifest backend matches production's WhiteNoise contract.
RUN DJANGO_SETTINGS_MODULE=static_settings PYTHONPATH=/app/container \
    python -m django collectstatic --noinput \
    && python -m config.runtime_requirements \
    && dpkg-query -W > /app/container/system-packages.txt \
    && chown 10001:10001 /run/dawana
USER 10001:10001
EXPOSE 8080
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD ["python", "/app/container/healthcheck.py"]
ENTRYPOINT ["/usr/bin/tini", "--", "python", "/app/container/entrypoint.py"]
