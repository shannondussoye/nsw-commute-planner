import os
import httpx
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("TFNSW_API_KEY")

# Major NSW GTFS Feeds
FEEDS = {
    "sydney_trains": "https://api.transport.nsw.gov.au/v1/gtfs/schedule/sydneytrains",
    "buses": "https://api.transport.nsw.gov.au/v1/gtfs/schedule/buses",
}

# OSM NSW Extract (Geofabrik)
OSM_URL = "https://download.geofabrik.de/australia/new-south-wales-latest.osm.pbf"

def download_file(url, path, headers=None):
    print(f"Downloading {url} to {path}...")
    with httpx.stream("GET", url, headers=headers, follow_redirects=True) as response:
        with open(path, "wb") as f:
            for chunk in response.iter_bytes():
                f.write(chunk)

if __name__ == "__main__":
    # Ensure directories exist
    os.makedirs("data/gtfs", exist_ok=True)
    os.makedirs("data/osm", exist_ok=True)

    # Download GTFS
    headers = {"Authorization": f"apikey {API_KEY}"}
    for name, url in FEEDS.items():
        download_file(url, f"data/gtfs/{name}.zip", headers=headers)
    
    # Download OSM
    download_file(OSM_URL, "data/osm/nsw.osm.pbf")
