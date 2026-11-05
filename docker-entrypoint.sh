#!/bin/sh
# Runs as root only long enough to make the data volume writable by the
# unprivileged app user, then drops privileges for the server itself.
# Existing installs have /app/data owned by root (the image used to run as
# root), so this chown is what lets them upgrade without manual steps.
set -e

if [ "$(id -u)" = "0" ]; then
    mkdir -p /app/data
    chown -R app:app /app/data 2>/dev/null \
        || echo "WARNING: could not chown /app/data — the app may not be able to write its database." >&2
    # setpriv keeps the environment, so HOME would still point at /root
    # (unwritable for app) — gunicorn keeps its control socket under HOME.
    HOME=/home/app exec setpriv --reuid=app --regid=app --init-groups "$@"
fi

exec "$@"
