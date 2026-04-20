FROM docker:27-cli AS docker_cli

FROM node:20-alpine AS assets_builder

WORKDIR /app

COPY package.json package-lock.json /app/
COPY scripts/build_vendor_assets.cjs /app/scripts/build_vendor_assets.cjs

RUN npm ci && npm run build:vendor

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=docker_cli /usr/local/bin/docker /usr/local/bin/docker

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app
COPY --from=assets_builder /app/static/vendor /app/static/vendor

RUN mkdir -p /app/executions /app/zip_archives

EXPOSE 8084

CMD ["gunicorn", "--bind", "0.0.0.0:8084", "--workers", "2", "--timeout", "120", "paste_server:app"]
