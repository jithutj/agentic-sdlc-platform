FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY pyproject.toml ./
COPY requirements.lock ./
COPY app ./app
COPY windmill ./windmill
RUN pip install --no-cache-dir -c requirements.lock .
USER 65532:65532
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"]

FROM base AS test
USER root
RUN pip install --no-cache-dir -c requirements.lock '.[dev]'
COPY tests ./tests
COPY scripts ./scripts
USER 65532:65532
CMD ["pytest", "-q", "-p", "no:cacheprovider"]

# Keep a plain `docker build .` producing the original API runtime.
FROM base AS runtime
