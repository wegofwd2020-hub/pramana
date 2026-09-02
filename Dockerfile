# Pramana API image.
#
# Multi-stage on purpose. The build needs `git` (two dependencies are installed
# from git+https) and a C toolchain; neither belongs in a running compliance
# system, so the runtime stage starts clean and copies only the virtualenv.
#
# The runtime stage installs WeasyPrint's native libraries. Without them
# /certificates/{id}/pdf and the audit binder fail *at request time* — the
# import is lazy, so a missing library surfaces to a user rather than at boot.

# ---------------------------------------------------------------------------
# Stage 1 — build
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# git: `wegofwd-llm` and `wegofwd-video` are git+https dependencies.
# build-essential + libffi-dev: source builds for the crypto/cffi wheels.
RUN apt-get update && apt-get install --no-install-recommends -y \
        git \
        build-essential \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build

# Dependency metadata first: this layer is cached until the dependency set
# changes, so ordinary source edits do not re-resolve the whole tree.
COPY pyproject.toml README.md ./
COPY pramana/__init__.py pramana/__init__.py
RUN pip install --no-cache-dir .

# Now the real source, and reinstall so the package contents are current.
COPY pramana/ pramana/
COPY alembic/ alembic/
COPY alembic.ini ./
RUN pip install --no-cache-dir --no-deps .

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# WeasyPrint's runtime dependencies. fonts-dejavu-core is not optional: the
# certificate and binder stylesheets name "DejaVu Sans"/"DejaVu Sans Mono", and
# a container without it renders boxes instead of text.
RUN apt-get update && apt-get install --no-install-recommends -y \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libgdk-pixbuf-2.0-0 \
        libcairo2 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Unprivileged: nothing here needs root, and this is a system whose product is
# the trustworthiness of its records.
RUN useradd --create-home --uid 10001 pramana

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=pramana:pramana alembic/ alembic/
COPY --chown=pramana:pramana alembic.ini ./
COPY --chown=pramana:pramana docs/frameworks/ docs/frameworks/

USER pramana
EXPOSE 8000

# --factory, matching `make run`: building the app at import time would resolve
# Settings on import. No --reload.
#
# --proxy-headers is not optional behind nginx. Without it uvicorn ignores
# X-Forwarded-For and every attestation records the proxy's address — SOX
# evidence that is well-formed, in the audit chain, and identifies nobody.
#
# --forwarded-allow-ips is scoped rather than "*". Trusting the header from any
# peer would let whoever can reach the port choose the IP that lands in the
# evidence, which is worse than recording the wrong one. FORWARDED_ALLOW_IPS
# names the actual proxy; the default covers a private Docker network.
#
# Migrations are deliberately NOT run here. With more than one replica the
# entrypoint would race, and 0007 (role seed) and 0009 (grants) are not things
# to apply concurrently. Run `alembic upgrade head` as a discrete step.
ENV FORWARDED_ALLOW_IPS=172.16.0.0/12
CMD ["sh", "-c", "exec uvicorn --factory pramana.api.app:create_app \
     --host 0.0.0.0 --port 8000 \
     --proxy-headers --forwarded-allow-ips \"$FORWARDED_ALLOW_IPS\""]
