#!/bin/bash
# Load environment variables safely (handles spaces and special chars)
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

java -Xmx${OTP_MEMORY:-12G} -jar otp.jar --load otp_data
