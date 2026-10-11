FROM python:3.12-slim AS service

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# The app is run from the source tree, the same way `uv run` does locally and
# the way the Vercel entrypoint does: `impl/data/*.json` ships with the sources,
# not with an installed wheel.
ENV PYTHONPATH=/app/src
EXPOSE 3000
CMD ["uvicorn", "openapi_server.main:app", "--host", "0.0.0.0", "--port", "3000", "--ws-ping-interval", "15", "--ws-ping-timeout", "30"]

# One-off catalog import (Amazon Reviews metadata -> WebP -> image storage).
# Run with: docker compose --profile ingest run --rm ingest
FROM service AS ingest
RUN pip install --no-cache-dir -r requirements-ingest.txt
