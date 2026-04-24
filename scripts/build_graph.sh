#!/bin/bash
set -euo pipefail

# Load environment variables (for OTP_BUILD_MEMORY)
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

# Download OTP JAR if not present
if [ ! -f "otp.jar" ]; then
  echo "Downloading OTP JAR..."
  curl -L https://repo1.maven.org/maven2/org/opentripplanner/otp/2.5.0/otp-2.5.0-shaded.jar -o otp.jar
fi

# Prepare OTP data directory
mkdir -p otp_data
rm -f otp_data/*.gtfs.zip

for f in data/gtfs/*.zip; do
  if [ -f "$f" ]; then
    cp "$f" "otp_data/$(basename "$f" .zip).gtfs.zip"
  fi
done

# Guard: ensure OSM data exists before proceeding
if ! ls data/osm/*.pbf 1>/dev/null 2>&1; then
  echo "[ERROR] No OSM .pbf file found in data/osm/. Run: python scripts/download_data.py"
  exit 1
fi
cp data/osm/*.pbf otp_data/

# Build the graph (configurable via OTP_BUILD_MEMORY in .env, default 12G)
java -Xmx${OTP_BUILD_MEMORY:-12G} -jar otp.jar --build --save otp_data
