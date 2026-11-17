FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
USER 65532:65532
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"]

FROM base AS test
USER root
RUN pip install --no-cache-dir '.[dev]'
COPY tests ./tests
USER 65532:65532
CMD ["pytest", "-q", "-p", "no:cacheprovider"]

# Keep a plain `docker build .` producing the original API runtime.
FROM base AS runtime
