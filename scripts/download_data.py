#!/usr/bin/env python3
"""Download GTFS timetable bundle and OSM extract for OTP graph building.

Uses ETag/Last-Modified caching to skip downloads when data hasn't changed.
Exit codes:
  0 — at least one file was updated
  1 — everything is already current (no changes)
  2 — an error occurred
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("TFNSW_API_KEY")

# TfNSW "Timetables Complete GTFS" — single bundle with all operators
GTFS_BUNDLE_URL = "https://api.transport.nsw.gov.au/v1/publictransport/timetables/complete/gtfs"
GTFS_BUNDLE_PATH = "data/gtfs/gtfs_bundle.zip"

# OSM NSW Extract (OpenStreetMap.fr mirror)
OSM_URL = "https://download.openstreetmap.fr/extracts/oceania/australia/new_south_wales-latest.osm.pbf"
OSM_PATH = "data/osm/nsw.osm.pbf"

MANIFEST_PATH = "data/.manifest.json"


def load_manifest():
    """Load the cached ETag/Last-Modified manifest."""
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, "r") as f:
            return json.load(f)
    return {}


def save_manifest(manifest):
    """Persist the manifest atomically."""
    tmp_path = MANIFEST_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(manifest, f, indent=2)
    os.rename(tmp_path, MANIFEST_PATH)


def check_for_update(url, manifest_key, manifest, headers=None):
    """Send a HEAD request and compare ETag/Last-Modified against the manifest.

    Returns (needs_update: bool, new_meta: dict).
    """
    if headers is None:
        headers = {}
    headers["User-Agent"] = "Mozilla/5.0 (compatible; NSWCommuteBot/1.0)"

    try:
        response = httpx.head(url, headers=headers, follow_redirects=True, timeout=30.0)
        if response.status_code in [403, 404]:
            print(f"  [WARN] HEAD request returned {response.status_code} for {url}")
            # Can't determine freshness, assume update needed
            return True, {}
    except Exception as e:
        print(f"  [WARN] HEAD request failed for {url}: {e}")
        # Can't determine freshness, assume update needed
        return True, {}

    remote_etag = response.headers.get("ETag")
    remote_modified = response.headers.get("Last-Modified")

    cached = manifest.get(manifest_key, {})
    cached_etag = cached.get("etag")
    cached_modified = cached.get("last_modified")

    new_meta = {
        "etag": remote_etag,
        "last_modified": remote_modified,
    }

    # If we have an ETag, use it as the primary comparison
    if remote_etag and cached_etag:
        if remote_etag == cached_etag:
            return False, new_meta
        return True, new_meta

    # Fall back to Last-Modified
    if remote_modified and cached_modified:
        if remote_modified == cached_modified:
            return False, new_meta
        return True, new_meta

    # No cache headers or no cached data — assume update needed
    return True, new_meta


def download_file(url, path, headers=None):
    """Download a file with atomic write (download to .tmp, then rename).

    Returns True on success, False on failure.
    """
    if headers is None:
        headers = {}
    headers["User-Agent"] = "Mozilla/5.0 (compatible; NSWCommuteBot/1.0)"

    tmp_path = path + ".tmp"
    print(f"  Downloading {url}...")

    try:
        with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=600.0) as response:
            if response.status_code in [403, 404]:
                print(f"  [SKIPPED] Access denied ({response.status_code}). "
                      "Ensure your API key is subscribed to this dataset in the TfNSW portal.")
                return False
            response.raise_for_status()

            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0

            with open(tmp_path, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = (downloaded / total) * 100
                        print(f"\r  Progress: {downloaded // (1024*1024)}MB / {total // (1024*1024)}MB ({pct:.0f}%)", end="", flush=True)

            print()  # newline after progress

        # Atomic swap
        os.rename(tmp_path, path)
        print(f"  Done: {path}")
        return True

    except Exception as e:
        print(f"\n  [ERROR] Failed to download: {e}")
        # Clean up partial download
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False


def main():
    parser = argparse.ArgumentParser(description="Download GTFS and OSM data for OTP")
    parser.add_argument("--skip-osm", action="store_true",
                        help="Skip the OSM download (for daily GTFS-only refresh)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Check for updates without downloading")
    args = parser.parse_args()

    if not API_KEY:
        print("[ERROR] TFNSW_API_KEY not set. Add it to your .env file.")
        sys.exit(2)

    # Ensure directories exist
    os.makedirs("data/gtfs", exist_ok=True)
    os.makedirs("data/osm", exist_ok=True)

    manifest = load_manifest()
    any_updated = False
    gtfs_headers = {"Authorization": f"apikey {API_KEY}"}

    # --- GTFS Bundle ---
    print("[GTFS] Checking for timetable updates...")
    needs_update, new_meta = check_for_update(
        GTFS_BUNDLE_URL, "gtfs_bundle", manifest, headers=gtfs_headers.copy()
    )

    if needs_update:
        if args.dry_run:
            print("  [DRY-RUN] GTFS bundle has updates available")
            any_updated = True
        else:
            success = download_file(GTFS_BUNDLE_URL, GTFS_BUNDLE_PATH, headers=gtfs_headers.copy())
            if success:
                manifest["gtfs_bundle"] = new_meta
                manifest["gtfs_bundle"]["downloaded_at"] = datetime.now(timezone.utc).isoformat()
                any_updated = True
            else:
                print("  [ERROR] GTFS download failed")
                sys.exit(2)
    else:
        print("  Already up to date (no changes detected)")

    # --- OSM ---
    if args.skip_osm:
        print("[OSM] Skipped (--skip-osm)")
    else:
        print("[OSM] Checking for map updates...")
        needs_update, new_meta = check_for_update(
            OSM_URL, "osm", manifest
        )

        if needs_update:
            if args.dry_run:
                print("  [DRY-RUN] OSM extract has updates available")
                any_updated = True
            else:
                success = download_file(OSM_URL, OSM_PATH)
                if success:
                    manifest["osm"] = new_meta
                    manifest["osm"]["downloaded_at"] = datetime.now(timezone.utc).isoformat()
                    any_updated = True
                else:
                    print("  [ERROR] OSM download failed")
                    sys.exit(2)
        else:
            print("  Already up to date (no changes detected)")

    # Save manifest
    if not args.dry_run:
        save_manifest(manifest)

    # Exit code: 0 = updated, 1 = no changes
    if any_updated:
        print("\n[RESULT] Data was updated" + (" (dry-run)" if args.dry_run else ""))
        sys.exit(0)
    else:
        print("\n[RESULT] All data is current, no downloads needed")
        sys.exit(1)


if __name__ == "__main__":
    main()
