#!/bin/bash
# =============================================================================
# refresh.sh — Automated GTFS/OSM data refresh for NSW Commute Calculator
#
# Workflow: detect changes → stop OTP → download → rebuild graph → start OTP
#
# Usage:
#   ./scripts/refresh.sh              # Daily GTFS-only refresh
#   ./scripts/refresh.sh --include-osm  # Weekly refresh including OSM
#   ./scripts/refresh.sh --dry-run      # Check for changes without acting
#
# Exit codes:
#   0 — refresh completed successfully (or data was already current)
#   1 — an error occurred
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOCKFILE="$PROJECT_DIR/.refresh.lock"
LOG_DIR="$PROJECT_DIR/logs"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python"

# Parse arguments
INCLUDE_OSM=false
DRY_RUN=false
for arg in "$@"; do
  case $arg in
    --include-osm) INCLUDE_OSM=true ;;
    --dry-run) DRY_RUN=true ;;
    *) echo "Unknown argument: $arg"; exit 1 ;;
  esac
done

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Timestamp helper
ts() {
  date '+%Y-%m-%d %H:%M:%S'
}

log() {
  echo "[$(ts)] $1"
}

# =============================================================================
# Lockfile — prevent overlapping runs
# =============================================================================
exec 200>"$LOCKFILE"
if ! flock -n 200; then
  log "ERROR: Another refresh is already running (lockfile: $LOCKFILE). Exiting."
  exit 1
fi

log "=========================================="
log "NSW Commute Data Refresh Starting"
log "  Mode: $(if $DRY_RUN; then echo 'DRY-RUN'; else echo 'LIVE'; fi)"
log "  OSM:  $(if $INCLUDE_OSM; then echo 'INCLUDED'; else echo 'SKIPPED'; fi)"
log "=========================================="

# =============================================================================
# Step 1: Check for updates and download
# =============================================================================
log "Step 1: Checking for data updates..."

DOWNLOAD_ARGS=""
if ! $INCLUDE_OSM; then
  DOWNLOAD_ARGS="--skip-osm"
fi
if $DRY_RUN; then
  DOWNLOAD_ARGS="$DOWNLOAD_ARGS --dry-run"
fi

cd "$PROJECT_DIR"
DOWNLOAD_EXIT=0
$VENV_PYTHON scripts/download_data.py $DOWNLOAD_ARGS || DOWNLOAD_EXIT=$?

if [ $DOWNLOAD_EXIT -eq 1 ]; then
  log "All data is current. No refresh needed."
  log "Refresh completed (no changes). Duration: 0s"
  exit 0
elif [ $DOWNLOAD_EXIT -eq 2 ]; then
  log "ERROR: Download failed. Aborting refresh."
  exit 1
elif [ $DOWNLOAD_EXIT -ne 0 ]; then
  log "ERROR: Download script returned unexpected exit code $DOWNLOAD_EXIT"
  exit 1
fi

if $DRY_RUN; then
  log "DRY-RUN complete. Updates are available but no action taken."
  exit 0
fi

log "New data downloaded successfully."

# =============================================================================
# Step 2: Stop OTP server
# =============================================================================
log "Step 2: Stopping OTP server..."

OTP_PID=$(pgrep -f "otp.jar --load" 2>/dev/null || true)
if [ -n "$OTP_PID" ]; then
  kill "$OTP_PID" 2>/dev/null || true
  # Wait for it to actually stop (max 30 seconds)
  WAIT_COUNT=0
  while kill -0 "$OTP_PID" 2>/dev/null && [ $WAIT_COUNT -lt 30 ]; do
    sleep 1
    WAIT_COUNT=$((WAIT_COUNT + 1))
  done
  if kill -0 "$OTP_PID" 2>/dev/null; then
    log "WARN: OTP didn't stop gracefully, forcing kill..."
    kill -9 "$OTP_PID" 2>/dev/null || true
    sleep 2
  fi
  log "  OTP server stopped (PID $OTP_PID)"
else
  log "  OTP server was not running"
fi

# =============================================================================
# Step 3: Rebuild the graph
# =============================================================================
log "Step 3: Building new transit graph..."
BUILD_START=$(date +%s)

if ! ./scripts/build_graph.sh; then
  log "ERROR: Graph build failed! The old graph.obj has been overwritten."
  log "ERROR: Manual intervention required — re-run build_graph.sh after fixing the issue."
  exit 1
fi

BUILD_END=$(date +%s)
BUILD_DURATION=$((BUILD_END - BUILD_START))
log "  Graph built successfully in ${BUILD_DURATION}s"

# =============================================================================
# Step 4: Start OTP server
# =============================================================================
log "Step 4: Starting OTP server..."

nohup ./scripts/run_server.sh >> "$LOG_DIR/otp_server.log" 2>&1 &

# Wait for the Java process to appear (the shell wrapper is not what we want)
sleep 5
OTP_PID=$(pgrep -f "otp.jar --load" 2>/dev/null || true)

if [ -z "$OTP_PID" ]; then
  log "ERROR: OTP server failed to start. Check $LOG_DIR/otp_server.log"
  exit 1
fi

log "  OTP server loading graph (PID $OTP_PID, this takes a few minutes)..."
log "  Tail logs: tail -f $LOG_DIR/otp_server.log"

log "=========================================="
log "Refresh completed successfully!"
log "  Graph build time: ${BUILD_DURATION}s"
log "  OTP server PID: $OTP_PID"
log "=========================================="
