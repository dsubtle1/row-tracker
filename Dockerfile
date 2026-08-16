FROM python:3.14-slim

WORKDIR /app

# Apply any OS-level security patches Debian has published since this base
# image tag was built. A vulnerability scan found several CVEs in OS packages
# shipped with the base image; most had no fix available at scan time, but
# this keeps every future rebuild current with whatever Debian does publish,
# without needing another manual Dockerfile change each time.
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

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

# Ensure the data directory exists (SQLite volume mount point)
RUN mkdir -p /app/data

EXPOSE 7376

CMD ["python", "app.py"]
