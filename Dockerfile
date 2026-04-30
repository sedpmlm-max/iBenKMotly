FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cache layer for fast rebuilds)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot source
COPY bot/ ./bot/

# Create dirs for credentials and memory persistence
RUN mkdir -p /app/dev-agent /root/.molty-royale

# Railway injects PORT env var; default 8080 for dashboard
EXPOSE 8080

# Railway: env vars injected at runtime, volumes configured via dashboard
# Local Docker: use docker run --env-file .env -v molty-data:/root/.molty-royale

CMD ["python", "-m", "bot.main"]
