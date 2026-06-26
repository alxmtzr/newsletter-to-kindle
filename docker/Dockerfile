# Stage 1: Python builder
FROM python:3.12-slim AS builder
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e ".[dev]" 2>/dev/null || \
    pip install --no-cache-dir -e .

# Stage 2: Runtime with JRE for EPUBCheck
FROM eclipse-temurin:21-jre-alpine AS runtime

# Install Python
RUN apk add --no-cache python3 py3-pip

# Copy installed Python packages and app from builder
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin/python3.12 /usr/local/bin/python3.12
RUN ln -sf /usr/local/bin/python3.12 /usr/local/bin/python3

# EPUBCheck
ARG EPUBCHECK_VERSION=5.1.0
RUN mkdir -p /opt/epubcheck && \
    wget -q "https://github.com/w3c/epubcheck/releases/download/v${EPUBCHECK_VERSION}/epubcheck-${EPUBCHECK_VERSION}.zip" \
         -O /tmp/epubcheck.zip && \
    unzip /tmp/epubcheck.zip -d /tmp/epubcheck_extract && \
    cp /tmp/epubcheck_extract/epubcheck-${EPUBCHECK_VERSION}/epubcheck.jar /opt/epubcheck/ && \
    rm -rf /tmp/epubcheck.zip /tmp/epubcheck_extract

# App source
WORKDIR /app
COPY --from=builder /app /app
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
