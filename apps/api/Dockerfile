FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry (pinned for reproducible builds)
RUN pip install --no-cache-dir poetry==2.5.2

# Copy poetry files
COPY pyproject.toml poetry.lock* ./

# Install Python dependencies.
# PYTHON_KEYRING_BACKEND: Poetry does not need a keyring for public packages,
# and probing the system keyring can crash inside containers.
RUN export PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring && \
    poetry config virtualenvs.create false && \
    poetry install --no-root --no-directory

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Health check: stdlib-only probe, fails on non-2xx responses and timeouts.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "/app/healthcheck.py"]

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
