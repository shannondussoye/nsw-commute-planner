# Design Spec: NSW Local Commute Calculator

A high-performance, local public transport routing engine for the entire state of New South Wales (NSW) using OpenTripPlanner (OTP) and Python.

## 1. Overview
The system will provide a way to calculate the fastest public transport (and walking) commute times between two sets of coordinates (latitude/longitude) across NSW. It avoids external API rate limits by running a local instance of OpenTripPlanner.

## 2. Architecture
*   **Routing Engine:** OpenTripPlanner (OTP) v2.x (Java-based).
*   **Client Interface:** Python 3.10+ using `asyncio` and `httpx`.
*   **Data Sources:**
    *   **Transit (GTFS):** Transport for NSW (TfNSW) Open Data (All bundles: Trains, Buses, Light Rail, Ferries, Regional).
    *   **Road/Path Network (OSM):** OpenStreetMap (NSW PBF extract).
*   **Host Environment:** Local machine with 16GB+ RAM.

## 3. Data Flow & Components

### Phase 1: Build (One-time or Periodic)
1.  **Download:** Automated scripts to fetch the latest GTFS bundles from TfNSW and the OSM PBF from a provider like Geofabrik.
2.  **Graph Build:** Run OTP's graph builder to merge GTFS and OSM into a single `graph.obj` file.
    *   *Memory requirement:* ~12GB heap (`-Xmx12G`).

### Phase 2: Server (Persistent)
1.  **Launch:** Start the OTP server loading the pre-built `graph.obj`.
2.  **API:** Exposes a GraphQL endpoint (defaulting to `http://localhost:8080/otp/routers/default/index/graphql`).

### Phase 3: Client (Querying)
1.  **Input:** Origin (lat, lon), Destination (lat, lon), Date, Time.
2.  **Request:** Python client sends an asynchronous GraphQL query to the local OTP server.
3.  **Processing:** Extracts the `duration` and `startTime`/`endTime` of the fastest itinerary.
4.  **Output:** Returns a JSON object with the commute details.

## 4. Key Features & Constraints
*   **Parallelism:** Python client uses `asyncio` to handle multiple concurrent routing requests.
*   **Modes:** Public Transport (Transit) + Walking (Access/Egress).
*   **Performance:** Local execution allows for high-throughput queries without rate limiting.
*   **Reliability:** Standardized JSON error handling for "no route found" or server timeouts.

## 5. Testing Strategy
*   **Data Validation:** Verify the graph build completes without errors.
*   **Accuracy Check:** Compare a few sample routes against the official Trip Planner website.
*   **Load Testing:** Measure response times for parallel queries (aiming for <100ms per route once the server is warm).
