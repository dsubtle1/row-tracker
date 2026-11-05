FROM python:3.13-slim

WORKDIR /app

# No .pyc files (the code dir isn't writable by the app user anyway) and
# unbuffered output so logs reach `docker compose logs` immediately.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Apply any OS-level security patches Debian has published since this base
# image tag was built. A vulnerability scan found several CVEs in OS packages
# shipped with the base image; most had no fix available at scan time, but
# this keeps every future rebuild current with whatever Debian does publish,
# without needing another manual Dockerfile change each time.
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

# Unprivileged user the server runs as (see docker-entrypoint.sh).
RUN groupadd --system app && useradd --system --gid app --create-home --home-dir /home/app app

# Install dependencies
COPY requirements.txt .
# The base image bundles whatever pip/setuptools/wheel version was current
# when that image tag was published. A vulnerability scan found known CVEs in
# those bundled versions (and jaraco-context, a pip dependency) — upgrade the
# build toolchain itself before installing anything else.
RUN pip install --no-cache-dir --upgrade pip setuptools wheel jaraco.context
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Code stays root-owned (the app user can read it but never modify it);
# a+rX also covers files an editor saved owner-only on the build host.
# Data directory is the one place the app user writes.
RUN chmod -R a+rX /app && mkdir -p /app/data && chown app:app /app/data

EXPOSE 7376

HEALTHCHECK --interval=60s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7376/faq', timeout=4)" || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]

# One worker on purpose: the nightly-job scheduler runs inside the app
# process, so a second worker would run every sync/backup twice. Threads
# give concurrency instead. Long timeout covers a first-run full C2 sync.
CMD ["gunicorn", "--bind", "0.0.0.0:7376", "--workers", "1", "--threads", "8", \
     "--timeout", "180", "--graceful-timeout", "30", \
     "--access-logfile", "-", "app:create_app()"]
