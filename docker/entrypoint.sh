#!/bin/bash
set -e

# Ensure data directory exists
mkdir -p /app/data/epubs

# Touch log file so tail works immediately
touch /var/log/newsletter-kindle.log

# Start cron daemon (Debian)
service cron start

# Keep container alive and stream logs
exec tail -f /var/log/newsletter-kindle.log
