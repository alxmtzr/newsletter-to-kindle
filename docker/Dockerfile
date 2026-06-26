# Stage 1: Build stage — only used to download EPUBCheck and its dependencies
FROM eclipse-temurin:21-jre-alpine AS jre

ARG EPUBCHECK_VERSION=5.1.0
RUN apk add --no-cache wget unzip && \
    wget -q "https://github.com/w3c/epubcheck/releases/download/v${EPUBCHECK_VERSION}/epubcheck-${EPUBCHECK_VERSION}.zip" \
         -O /tmp/epubcheck.zip && \
    unzip /tmp/epubcheck.zip -d /tmp/epubcheck_extract && \
    mv "/tmp/epubcheck_extract/epubcheck-${EPUBCHECK_VERSION}" /opt/epubcheck && \
    rm -rf /tmp/epubcheck.zip /tmp/epubcheck_extract

# Stage 2: Runtime — Python + JRE + app
FROM python:3.12-slim AS runtime

# Install JRE (for EPUBCheck)
RUN apt-get update && \
    apt-get install -y --no-install-recommends default-jre-headless cron && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy EPUBCheck jar from jre stage
COPY --from=jre /opt/epubcheck /opt/epubcheck

# Install Python dependencies
WORKDIR /app
COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --root-user-action=ignore .

# Copy app config and cron
COPY config.yaml .
COPY docker/crontab /etc/cron.d/newsletter-kindle
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && \
    chmod 0644 /etc/cron.d/newsletter-kindle && \
    crontab /etc/cron.d/newsletter-kindle

ENV TZ=Europe/Berlin
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

VOLUME ["/app/data"]

ENTRYPOINT ["/entrypoint.sh"]
