# Stage 1: Python builder — install dependencies
FROM python:3.12-slim AS builder
WORKDIR /app
COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Stage 2: Runtime with JRE for EPUBCheck
FROM eclipse-temurin:21-jre-alpine AS runtime

# Install Python + pip from Alpine repos
RUN apk add --no-cache python3 py3-pip

# Copy installed Python packages from builder into the Alpine Python's site-packages
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/lib/python3.12/site-packages

# EPUBCheck
ARG EPUBCHECK_VERSION=5.1.0
RUN apk add --no-cache wget unzip && \
    mkdir -p /opt/epubcheck && \
    wget -q "https://github.com/w3c/epubcheck/releases/download/v${EPUBCHECK_VERSION}/epubcheck-${EPUBCHECK_VERSION}.zip" \
         -O /tmp/epubcheck.zip && \
    unzip /tmp/epubcheck.zip -d /tmp/epubcheck_extract && \
    cp "/tmp/epubcheck_extract/epubcheck-${EPUBCHECK_VERSION}/epubcheck.jar" /opt/epubcheck/ && \
    rm -rf /tmp/epubcheck.zip /tmp/epubcheck_extract && \
    apk del wget unzip

# App source
WORKDIR /app
COPY src/ src/
COPY config.yaml .

# Cron
COPY docker/crontab /etc/crontabs/root
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV TZ=Europe/Berlin
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

VOLUME ["/app/data"]

ENTRYPOINT ["/entrypoint.sh"]
