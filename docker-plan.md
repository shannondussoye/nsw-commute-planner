# Docker Migration Plan — NSW Commute Planner

## Goal

Containerise the entire NSW Commute Planner stack so that setup reduces from a multi-step manual process (install Java, Python, download data, build graph, start server) to a single `docker compose up`.

---

## Current Architecture

```
Host machine
├── Python 3.13 + venv      (download_data.py, cli.py, client.py)
├── Java 17+                (OTP 2.5.0 — otp.jar)
├── data/gtfs/              (~100MB GTFS zip)
├── data/osm/               (~600MB OSM pbf)
├── otp_data/graph.obj      (~1-2GB compiled graph)
├── scripts/refresh.sh      (cron-driven orchestrator)
└── logs/                   (runtime logs)
```

### Key Constraints

| Concern | Detail |
|---|---|
| **Memory** | OTP needs 12GB heap for both build and serve |
| **Build time** | Graph compilation takes 5–10 min |
| **Data size** | ~2GB total (GTFS + OSM + graph.obj) |
| **Secrets** | `TFNSW_API_KEY` needed only at download time |
| **Refresh** | GTFS updates daily; OSM weekly; requires stop → rebuild → start cycle |

---

## Proposed Architecture

Two containers managed by Docker Compose, sharing a data volume:

```
┌─────────────────────────────────────────────────────┐
│  docker compose                                     │
│                                                     │
│  ┌──────────────┐        ┌───────────────────────┐  │
│  │  otp-server   │        │  data-manager          │  │
│  │  Java 17      │        │  Python 3.13           │  │
│  │  OTP 2.5.0    │        │  download_data.py      │  │
│  │  port 8080    │        │  build_graph.sh         │  │
│  │               │        │  refresh entrypoint     │  │
│  └──────┬───────┘        └──────────┬────────────┘  │
│         │                           │                │
│         └───────────┬───────────────┘                │
│                     │                                │
│              ┌──────▼──────┐                         │
│              │  otp-data    │  (named volume)         │
│              │  graph.obj   │                         │
│              │  *.gtfs.zip  │                         │
│              │  *.osm.pbf   │                         │
│              └─────────────┘                         │
│                                                     │
│              ┌─────────────┐                         │
│              │  app-data    │  (named volume)         │
│              │  data/gtfs/  │                         │
│              │  data/osm/   │                         │
│              │  .manifest   │                         │
│              └─────────────┘                         │
└─────────────────────────────────────────────────────┘
```

### Why Two Containers (Not One)

- **Separation of concerns** — the OTP server is a long-running Java process; the data manager is a short-lived Python process that runs on a schedule. Mixing them in one container makes process management messy (PID 1 issues, signal handling, supervisord overhead).
- **Independent restarts** — when data refreshes, only the OTP container needs to restart. The data-manager does its work then exits.
- **Smaller attack surface** — the server container doesn't need Python, pip, or API keys.

---

## Implementation Plan

### Phase 1: Dockerfiles

#### 1a. `Dockerfile.otp` — OTP Server

```dockerfile
FROM eclipse-temurin:17-jre-jammy

ARG OTP_VERSION=2.5.0
ENV OTP_MEMORY=12G

# Download OTP JAR at build time (cached in image layer)
RUN curl -fsSL \
    "https://repo1.maven.org/maven2/org/opentripplanner/otp/${OTP_VERSION}/otp-${OTP_VERSION}-shaded.jar" \
    -o /opt/otp.jar

WORKDIR /var/otp

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8080/otp/routers/default || exit 1

ENTRYPOINT ["sh", "-c", "java -Xmx${OTP_MEMORY} -jar /opt/otp.jar --load /var/otp"]
```

**Key decisions:**
- `eclipse-temurin:17-jre-jammy` — official, minimal JRE image (~200MB). No full JDK needed since we only run OTP, not compile it.
- OTP JAR baked into the image — avoids re-downloading on every restart. Version pinned via build arg.
- `--start-period=120s` on healthcheck — OTP takes 1–2 minutes to load the graph; this prevents Docker from killing it during startup.
- `/var/otp` is the mount point for the shared volume containing `graph.obj`.

#### 1b. `Dockerfile.data` — Data Manager

```dockerfile
FROM python:3.13-slim-bookworm

# Install Java JRE for graph building and curl for health checks
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        openjdk-17-jre-headless curl && \
    rm -rf /var/lib/apt/lists/*

ARG OTP_VERSION=2.5.0
ENV OTP_BUILD_MEMORY=12G

# Download OTP JAR (needed for graph build)
RUN curl -fsSL \
    "https://repo1.maven.org/maven2/org/opentripplanner/otp/${OTP_VERSION}/otp-${OTP_VERSION}-shaded.jar" \
    -o /opt/otp.jar

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/ ./scripts/
COPY src/ ./src/

# Default: run the refresh workflow
ENTRYPOINT ["./scripts/docker-refresh.sh"]
```

**Key decisions:**
- `python:3.13-slim` + `openjdk-17-jre-headless` — needs both runtimes (Python for download, Java for graph build). Using slim base keeps it under ~400MB.
- OTP JAR duplicated here because graph building requires it. This is the tradeoff of two containers — ~180MB duplicated, but it keeps the server image clean.
- A new `docker-refresh.sh` entrypoint replaces `refresh.sh` — no more `pgrep`/`nohup`/lockfile logic (Docker handles all of that).

---

### Phase 2: Docker Compose

#### `docker-compose.yml`

```yaml
services:
  otp-server:
    build:
      context: .
      dockerfile: Dockerfile.otp
    container_name: nsw-otp-server
    ports:
      - "8080:8080"
    environment:
      - OTP_MEMORY=${OTP_MEMORY:-12G}
    volumes:
      - otp-data:/var/otp
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 14G
    depends_on:
      data-init:
        condition: service_completed_successfully

  # One-shot container: downloads data + builds graph, then exits
  data-init:
    build:
      context: .
      dockerfile: Dockerfile.data
    container_name: nsw-data-init
    environment:
      - TFNSW_API_KEY=${TFNSW_API_KEY}
      - OTP_BUILD_MEMORY=${OTP_BUILD_MEMORY:-12G}
    volumes:
      - otp-data:/var/otp
      - app-data:/app/data
    command: ["./scripts/docker-init.sh"]
    deploy:
      resources:
        limits:
          memory: 14G

volumes:
  otp-data:
  app-data:
```

**Key decisions:**
- `data-init` uses `service_completed_successfully` — OTP won't start until the graph exists. On first run, this means: download → build → then OTP starts. On subsequent runs, if the graph already exists in the volume, `data-init` exits immediately and OTP starts.
- `restart: unless-stopped` on OTP only — the data containers are one-shot.
- `memory: 14G` limit — gives 2GB headroom above the 12G Java heap for OS/GC overhead.
- API key only injected into `data-init`, never into `otp-server`.

---

### Phase 3: New Entrypoint Scripts

#### `scripts/docker-init.sh` — First-Run Bootstrap

```bash
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
```

#### `scripts/docker-refresh.sh` — Scheduled Data Refresh

```bash
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
# This is done externally (see cron section below)
```

---

### Phase 4: Automated Refresh via Cron (Host-Side)

Since the refresh needs to restart the OTP container, the cron job runs on the **host**, not inside a container:

```cron
# Daily GTFS refresh at 3:00 AM AEST
0 3 * * * cd /home/shannon/Workspace/playground/tfnsw && docker compose run --rm data-init ./scripts/docker-refresh.sh && docker compose restart otp-server >> logs/refresh.log 2>&1

# Weekly full refresh (Sunday 2:00 AM AEST)
0 2 * * 0 cd /home/shannon/Workspace/playground/tfnsw && docker compose run --rm data-init ./scripts/docker-refresh.sh --include-osm && docker compose restart otp-server >> logs/refresh.log 2>&1
```

**Why host-side cron, not in-container cron:**
- Restarting the OTP container requires Docker socket access — mounting `/var/run/docker.sock` into a container is a security anti-pattern.
- Host cron is simpler, more observable, and matches the existing pattern.

---

### Phase 5: CLI Access

The CLI (`cli.py`) talks to OTP over HTTP, so it works unchanged from the host:

```bash
export PYTHONPATH=src
python src/nsw_commute/cli.py --search "Central"
```

Alternatively, run it inside the data-manager container:

```bash
docker compose run --rm data-init python src/nsw_commute/cli.py --search "Central"
```

Or add a convenience `cli` service to `docker-compose.yml`:

```yaml
  cli:
    build:
      context: .
      dockerfile: Dockerfile.data
    environment:
      - OTP_URL=http://otp-server:8080
    volumes:
      - app-data:/app/data
    entrypoint: ["python", "src/nsw_commute/cli.py"]
    profiles: ["cli"]
    network_mode: service:otp-server
```

Usage: `docker compose run --rm cli --search "Central"`

> **Note:** This requires a small change to `OTPClient.__init__` to read `OTP_URL` from env:
> ```python
> import os
> class OTPClient:
>     def __init__(self, base_url=None):
>         base_url = base_url or os.getenv("OTP_URL", "http://localhost:8080")
> ```

---

## Files to Create

| File | Purpose |
|---|---|
| `Dockerfile.otp` | OTP server image (Java + OTP JAR) |
| `Dockerfile.data` | Data manager image (Python + Java + scripts) |
| `docker-compose.yml` | Service orchestration |
| `scripts/docker-init.sh` | First-run bootstrap (download + build) |
| `scripts/docker-refresh.sh` | Refresh entrypoint (replaces `refresh.sh` logic for Docker) |
| `.dockerignore` | Exclude `venv/`, `otp_data/`, `data/`, `logs/`, `.git/` |

## Files to Modify

| File | Change |
|---|---|
| `src/nsw_commute/client.py` | Read `OTP_URL` from env with `localhost:8080` fallback |
| `.env.example` | Add `OTP_URL` variable |
| `README.md` | Add Docker section with `docker compose up` instructions |

---

## Rollout Sequence

```
Phase 1: Write Dockerfiles                    [no existing code changes]
Phase 2: Write docker-compose.yml             [no existing code changes]
Phase 3: Write docker-init.sh, docker-refresh.sh   [no existing code changes]
Phase 4: Modify client.py (OTP_URL env var)   [backward compatible — defaults to localhost]
Phase 5: Write .dockerignore                  [no existing code changes]
Phase 6: Update README.md                     [documentation only]
Phase 7: Test — docker compose up from clean state
Phase 8: Test — refresh cycle (docker compose run data-init + restart)
Phase 9: Update crontab.example with Docker commands
```

Every phase is independently committable. The bare-metal setup continues to work throughout — Docker is purely additive.

---

## Verification Plan

### Automated Tests (unchanged)

```bash
PYTHONPATH=src ./venv/bin/pytest tests/ -v
```

These test the Python client with mocked HTTP — no Docker dependency.

### Docker Smoke Tests

```bash
# 1. Full bootstrap from scratch (clean volumes)
docker compose down -v
docker compose up -d
# Wait for healthcheck to pass (~2-3 min)
docker compose ps   # otp-server should show "healthy"

# 2. CLI works inside Docker network
docker compose run --rm cli --list

# 3. CLI works from host
PYTHONPATH=src python src/nsw_commute/cli.py --list

# 4. Refresh cycle
docker compose run --rm data-init ./scripts/docker-refresh.sh --dry-run

# 5. Graph survives container restart
docker compose restart otp-server
# Wait for healthy again
docker compose ps
```

---

## Decisions Made

1. **OTP JAR Version**: Pinned to 2.5.0 by default using a build argument, allowing it to be overridden for upgrades without changing the core Dockerfile.
2. **Log Persistence**: Relies on standard Docker logging (`docker compose logs`); no need for complex file-based volume mounts for logs.
3. **Hosting Target**: Since this will be deployed to a VPS and a headless Linux machine, the architecture is tailored to allow images to be built once (e.g., via GitHub Actions or on one machine) and pushed to a registry (like GitHub Container Registry `ghcr.io`). The target machines can then simply pull the pre-built images and run `docker compose up`, executing only the data fetch and graph build locally using the pre-packaged OTP environment.
