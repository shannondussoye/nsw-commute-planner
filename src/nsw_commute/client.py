import httpx
import asyncio
from datetime import datetime

class OTPClient:
    def __init__(self, base_url="http://localhost:8080"):
        self.url = f"{base_url}/otp/routers/default/index/graphql"

    def format_time(self, ms):
        if ms is None:
            return None
        return datetime.fromtimestamp(ms / 1000).strftime('%Y-%m-%d %H:%M:%S')

    def format_duration(self, seconds):
        if seconds is None:
            return 0
        return round(seconds / 60, 1)

    def _format_place(self, place):
        if isinstance(place, (list, tuple)):
            return f"{place[0]}, {place[1]}"
        else:
            return str(place)

    def _is_true_station(self, station_data):
        """A 'True Station' has at least one RAIL or SUBWAY platform."""
        stops = station_data.get("stops", [])
        for stop in stops:
            mode = stop.get("vehicleMode")
            if mode in ["RAIL", "SUBWAY"]:
                return True
        return False

    async def search_stations(self, name):
        """Searches for true Rail/Metro stations by name."""
        query = f"""
        {{
          stops(name: "{name}") {{
            locationType
            parentStation {{
              gtfsId
              name
              lat
              lon
              stops {{
                vehicleMode
              }}
            }}
            gtfsId
            name
            lat
            lon
            stops {{
              vehicleMode
            }}
          }}
        }}
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.url, json={"query": query}, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                raw_stops = data.get("data", {}).get("stops", [])
                
                unique_stations = {}
                for item in raw_stops:
                    target = None
                    if item.get("parentStation"):
                        target = item["parentStation"]
                    elif item.get("locationType") == "STATION":
                        target = item
                    
                    if target and self._is_true_station(target):
                        unique_stations[target["gtfsId"]] = {
                            "id": target["gtfsId"],
                            "name": target["name"],
                            "lat": target["lat"],
                            "lon": target["lon"]
                        }
                
                final_results = [
                    s for s in unique_stations.values() 
                    if name.lower() in s["name"].lower()
                ]
                
                return sorted(final_results, key=lambda x: x["name"])
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                return {"error": str(e)}

    async def list_stations(self):
        """Retrieves a list of all Parent Stations served by Rail or Metro."""
        query = """
        {
          stations {
            gtfsId
            name
            lat
            lon
            stops {
              vehicleMode
            }
          }
        }
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.url, json={"query": query}, timeout=15.0)
                response.raise_for_status()
                data = response.json()
                results = data.get("data", {}).get("stations", [])
                
                true_stations = [
                    {
                        "id": r["gtfsId"],
                        "name": r["name"],
                        "lat": r["lat"],
                        "lon": r["lon"]
                    }
                    for r in results 
                    if self._is_true_station(r)
                ]
                
                return sorted(true_stations, key=lambda x: x["name"])
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                return {"error": str(e)}

    def build_query(self, from_place, to_place, date, time, arriveBy=False):
        from_str = self._format_place(from_place)
        to_str = self._format_place(to_place)
        
        return f"""
        {{
          plan(
            fromPlace: "{from_str}"
            toPlace: "{to_str}"
            date: "{date}"
            time: "{time}"
            arriveBy: {str(arriveBy).lower()}
            transportModes: [
              {{ mode: TRANSIT }}, 
              {{ mode: BUS }}, 
              {{ mode: RAIL }}, 
              {{ mode: SUBWAY }}, 
              {{ mode: FERRY }}, 
              {{ mode: TRAM }}, 
              {{ mode: WALK }}
            ]
            numItineraries: 5
            walkSpeed: 1.1
            walkReluctance: 1.5
          ) {{
            itineraries {{
              duration
              startTime
              endTime
              legs {{
                mode
                duration
                startTime
                endTime
                interlineWithPreviousLeg
                from {{ name }}
                to {{ name }}
                route {{ shortName longName }}
              }}
            }}
          }}
        }}
        """

    def _merge_stay_on_board_legs(self, legs):
        if not legs:
            return []
        
        merged = []
        for leg in legs:
            if leg.get("interlineWithPreviousLeg") and merged:
                prev = merged[-1]
                prev["duration_minutes"] = round(prev["duration_minutes"] + leg["duration_minutes"], 1)
                prev["end_time"] = leg["end_time"]
                prev["to"] = leg["to"]
            else:
                merged.append(leg)
        return merged

    async def get_itineraries(self, from_place, to_place, date, time, arrive_by=False):
        query = self.build_query(from_place, to_place, date, time, arrive_by)
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.url, json={"query": query}, timeout=30.0)
                response.raise_for_status()
                data = response.json()
                
                if "errors" in data:
                    return {"error": data["errors"][0].get("message", "Unknown GraphQL error")}
                
                if not data.get("data", {}).get("plan", {}).get("itineraries"):
                    return {"error": "no_route_found"}
                
                raw_itineraries = data["data"]["plan"]["itineraries"]
                
                processed_results = []
                for plan in raw_itineraries:
                    mode_breakdown = {}
                    detailed_legs = []
                    
                    for leg in plan.get("legs", []):
                        mode = leg["mode"]
                        dur_min = self.format_duration(leg["duration"])
                        mode_breakdown[mode] = round(mode_breakdown.get(mode, 0) + dur_min, 1)
                        
                        detailed_legs.append({
                            "mode": mode,
                            "duration_minutes": dur_min,
                            "start_time": self.format_time(leg["startTime"]),
                            "end_time": self.format_time(leg["endTime"]),
                            "from": leg["from"]["name"],
                            "to": leg["to"]["name"],
                            "route": leg["route"]["shortName"] if leg["route"] else None,
                            "interlineWithPreviousLeg": leg.get("interlineWithPreviousLeg", False)
                        })
                    
                    merged_legs = self._merge_stay_on_board_legs(detailed_legs)
                    
                    processed_results.append({
                        "summary": {
                            "duration_minutes": self.format_duration(plan["duration"]),
                            "start_time": self.format_time(plan["startTime"]),
                            "end_time": self.format_time(plan["endTime"])
                        },
                        "mode_breakdown": mode_breakdown,
                        "detailed_legs": merged_legs
                    })
                
                processed_results.sort(key=lambda x: x["summary"]["end_time"])
                return processed_results
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                return {"error": str(e)}
