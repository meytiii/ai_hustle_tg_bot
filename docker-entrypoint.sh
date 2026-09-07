#!/bin/sh
set -e

# Ensure persistent data directory exists and has full read/write permissions
mkdir -p /app/data
chmod 777 /app/data 2>/dev/null || true

# Execute container command
exec "$@"
