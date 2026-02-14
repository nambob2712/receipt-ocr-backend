FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for asyncpg / psycopg2
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Railway injects $PORT at runtime; default to 8000 for local
ENV PORT=8000
EXPOSE ${PORT}

# Railway overrides this via railway.json startCommand
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
