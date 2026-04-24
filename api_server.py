import sys
import os
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from typing import Optional, List, Dict, Any
from datetime import datetime

# Add the 'src' directory to the Python path to import nsw_commute
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from nsw_commute.client import OTPClient

app = FastAPI(
    title="NSW Commute API",
    description="Microservice wrapper for OpenTripPlanner",
    version="1.0.0"
)

client = OTPClient()

@app.get("/route")
async def get_route(
    from_lat: Optional[float] = Query(None, description="Origin latitude"),
    from_lon: Optional[float] = Query(None, description="Origin longitude"),
    from_id: Optional[str] = Query(None, description="Origin Station/Stop ID (e.g., '1:200060')"),
    to_lat: Optional[float] = Query(None, description="Destination latitude"),
    to_lon: Optional[float] = Query(None, description="Destination longitude"),
    to_id: Optional[str] = Query(None, description="Destination Station/Stop ID"),
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format (defaults to today)"),
    time: Optional[str] = Query(None, description="Time in HH:mm format (defaults to now)"),
    arrive_by: bool = Query(False, description="Set to true if you want to arrive by the specified time")
):
    """
    Calculates the best multimodal commute route between two points.
    """
    # Determine Origin
    if from_id:
        origin = from_id
    elif from_lat is not None and from_lon is not None:
        origin = (from_lat, from_lon)
    else:
        raise HTTPException(status_code=400, detail="Must provide either from_id OR both from_lat and from_lon")

    # Determine Destination
    if to_id:
        destination = to_id
    elif to_lat is not None and to_lon is not None:
        destination = (to_lat, to_lon)
    else:
        raise HTTPException(status_code=400, detail="Must provide either to_id OR both to_lat and to_lon")

    # Defaults for date and time
    now = datetime.now()
    if not date:
        date = now.strftime("%Y-%m-%d")
    if not time:
        time = now.strftime("%H:%M")

    # Call the local OTP engine
    results = await client.get_itineraries(
        origin,
        destination,
        date,
        time,
        arrive_by
    )

    if isinstance(results, dict) and "error" in results:
        if results["error"] == "no_route_found":
            raise HTTPException(status_code=404, detail="No route found between these locations.")
        raise HTTPException(status_code=500, detail=results["error"])
        
    if not results:
        raise HTTPException(status_code=404, detail="No route found between these locations.")

    # Return the single best itinerary (fastest/earliest arrival)
    # The client already sorts them, so the first one is usually the optimal
    if isinstance(results, list) and len(results) > 0:
        return results[0]
    
    return results

@app.get("/stations/search")
async def search_stations(
    q: str = Query(..., description="Name of the station to search for (e.g., 'Central')")
):
    """Search for Train/Metro stations by name."""
    results = await client.search_stations(q)
    if isinstance(results, dict) and "error" in results:
        raise HTTPException(status_code=500, detail=results["error"])
    return results

@app.get("/stations")
async def list_stations():
    """List all parent Train/Metro stations."""
    results = await client.list_stations()
    if isinstance(results, dict) and "error" in results:
        raise HTTPException(status_code=500, detail=results["error"])
    return results

if __name__ == "__main__":
    uvicorn.run("api_server:app", host="0.0.0.0", port=8001, reload=True)
