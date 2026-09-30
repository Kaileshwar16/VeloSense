FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock requirements-iceberg.lock ./
RUN pip install --no-cache-dir -r requirements.lock -r requirements-iceberg.lock \
    && useradd --uid 10001 --create-home app \
    && mkdir -p /data/iceberg/warehouse && chown -R app:app /data/iceberg
COPY --chown=app:app . .
USER app
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "archive.cli", "consume"]
