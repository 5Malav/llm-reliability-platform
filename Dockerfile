# Small Linux + the same Python as our venv
FROM python:3.11-slim

# Print logs immediately; don't write .pyc cache files
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Libraries first, so code changes don't reinstall them
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# A normal user instead of root
RUN useradd --create-home appuser

# Our code, owned by that user (log_query writes to monitoring/query_log.jsonl)
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

# Use the port the platform gives us, else 8000.
# exec = uvicorn hears the stop signal directly, so langfuse.flush() runs on shutdown.
CMD ["sh", "-c", "exec uvicorn api.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
