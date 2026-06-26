#!/bin/sh
set -e

# Ensure data directory exists
mkdir -p /app/data/epubs

# Start cron in foreground
exec crond -f -L /var/log/newsletter-kindle.log
