FROM python:3.12-slim

WORKDIR /app
COPY worker/requirements.txt /tmp/worker-requirements.txt
COPY worker/requirements-dev.txt /tmp/worker-requirements-dev.txt
COPY api/requirements.txt /tmp/api-requirements.txt
COPY api/requirements-dev.txt /tmp/api-requirements-dev.txt
RUN pip install --no-cache-dir \
    -r /tmp/worker-requirements.txt \
    -r /tmp/worker-requirements-dev.txt \
    -r /tmp/api-requirements.txt \
    -r /tmp/api-requirements-dev.txt

COPY worker /app
COPY api/aose_api /app/aose_api
COPY api/alembic.ini /app/alembic.ini
COPY api/migrations /app/migrations
ENV PYTHONPATH=/app

CMD ["python", "-m", "aose_worker.run_worker"]
