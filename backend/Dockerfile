FROM python:3.12.10-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml ./

RUN python -m venv "${VIRTUAL_ENV}" \
    && pip install --upgrade pip

FROM base AS runtime

COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS test

COPY src ./src
COPY tests ./tests
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install ".[dev]"

CMD ["pytest", "-q"]
