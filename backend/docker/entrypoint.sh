#!/bin/sh
set -eu

echo "Applying Alembic migrations…"
alembic upgrade head

echo "Starting API on 0.0.0.0:8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
