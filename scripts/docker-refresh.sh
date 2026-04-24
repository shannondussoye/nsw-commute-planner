#!/bin/bash
set -euo pipefail

cd /app

DOWNLOAD_ARGS="${1:---skip-osm}"

# Check for updates
DOWNLOAD_EXIT=0
python scripts/download_data.py $DOWNLOAD_ARGS || DOWNLOAD_EXIT=$?

if [ $DOWNLOAD_EXIT -eq 1 ]; then
  echo "[refresh] Data is current. No rebuild needed."
  exit 0
elif [ $DOWNLOAD_EXIT -ne 0 ]; then
  echo "[refresh] ERROR: Download failed (exit $DOWNLOAD_EXIT)"
  exit 1
fi

echo "[refresh] New data downloaded. Rebuilding graph..."

# Copy updated data into OTP volume
rm -f /var/otp/*.gtfs.zip
for f in data/gtfs/*.zip; do
  [ -f "$f" ] && cp "$f" "/var/otp/$(basename "$f" .zip).gtfs.zip"
done
cp data/osm/*.pbf /var/otp/

# Rebuild graph
java -Xmx${OTP_BUILD_MEMORY:-12G} -jar /opt/otp.jar --build --save /var/otp

echo "[refresh] Graph rebuilt. Restarting OTP server..."

# Signal Compose to restart the OTP container
# This is done externally (see cron section in README)
