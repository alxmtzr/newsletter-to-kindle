#!/bin/bash
set -e

# Ensure data directory exists
mkdir -p /app/data/epubs

# Touch log file so tail works immediately
touch /var/log/newsletter-kindle.log

# Dump container env vars so cron jobs can source them
printenv | grep -v '^_=' > /etc/environment

# Start cron daemon (Debian)
service cron start

# Keep container alive and stream logs
exec tail -f /var/log/newsletter-kindle.log
