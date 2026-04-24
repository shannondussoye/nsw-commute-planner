#!/bin/bash
set -euo pipefail

# Skip if graph already exists (volume persists across restarts)
if [ -f /var/otp/graph.obj ]; then
  echo "[docker-init] Graph already exists. Skipping bootstrap."
  exit 0
fi

echo "[docker-init] First run — downloading data and building graph..."

cd /app
python scripts/download_data.py

# Copy data into OTP directory
mkdir -p /var/otp
rm -f /var/otp/*.gtfs.zip
for f in data/gtfs/*.zip; do
  [ -f "$f" ] && cp "$f" "/var/otp/$(basename "$f" .zip).gtfs.zip"
done
cp data/osm/*.pbf /var/otp/

# Build graph
java -Xmx${OTP_BUILD_MEMORY:-12G} -jar /opt/otp.jar --build --save /var/otp

echo "[docker-init] Bootstrap complete."
