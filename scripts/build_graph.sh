#!/bin/bash
# Download OTP JAR if not present
if [ ! -f "otp.jar" ]; then
  curl -L https://repo1.maven.org/maven2/org/opentripplanner/otp/2.5.0/otp-2.5.0-shaded.jar -o otp.jar
fi

# Move all data into one directory for OTP
mkdir -p otp_data
cp data/gtfs/*.zip otp_data/
cp data/osm/*.pbf otp_data/

# Build the graph
java -Xmx12G -jar otp.jar --build --save otp_data
