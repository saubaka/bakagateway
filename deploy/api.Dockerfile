FROM python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70 AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY backend/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
    && groupadd --gid 10001 gateway && useradd --uid 10001 --gid gateway --no-create-home gateway \
    && mkdir -p /app/data/avatars /app/keys && chown -R gateway:gateway /app/data /app/keys
COPY backend/app /app/app
COPY backend/migrations /app/migrations
COPY backend/wsgi.py /app/wsgi.py
USER gateway
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "30", "--access-logfile", "/dev/null", "wsgi:app"]

FROM base AS dev
CMD ["flask", "--app", "app:create_app", "run", "--host", "0.0.0.0", "--port", "8000", "--reload", "--no-debugger"]

FROM base AS production
