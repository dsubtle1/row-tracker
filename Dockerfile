FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure the data directory exists (SQLite volume mount point)
RUN mkdir -p /app/data

EXPOSE 7376

CMD ["python", "app.py"]
