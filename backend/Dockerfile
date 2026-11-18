# Sentinel API image (ENG-4). Runs migrations then Uvicorn.
# Chromium is installed for real checks/journeys inside the container.

FROM python:3.12-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
COPY docker/entrypoint.sh /entrypoint.sh

RUN python -m pip install --no-cache-dir -e . \
    && python -m playwright install --with-deps chromium \
    && sed -i 's/\r$//' /entrypoint.sh \
    && chmod +x /entrypoint.sh \
    && mkdir -p /app/data/screenshots

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
