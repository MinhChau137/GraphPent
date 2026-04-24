FROM python:3.11-slim

WORKDIR /app

# Install system deps (keep separate for layer caching)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl git && \
    rm -rf /var/lib/apt/lists/*

# Copy and install requirements early (before app code)
# This allows caching of pip dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 8000

# Use non-reload for production, with reload for development
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]