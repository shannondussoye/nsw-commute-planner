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

    def build_query(self, from_lat, from_lon, to_lat, to_lon, date, time, arriveBy=False):
        return f"""
        {{
          plan(
            from: {{ lat: {from_lat}, lon: {from_lon} }}
            to: {{ lat: {to_lat}, lon: {to_lon} }}
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
            walkReluctance: 1.75
            waitReluctance: 1.0
            transferPenalty: 180
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
                from {{ name }}
                to {{ name }}
                route {{ shortName longName }}
                stayOnBoard
                tripId
              }}
            }}
          }}
        }}
        """

    async def get_itineraries(self, from_coords, to_coords, date, time, arrive_by=False):
        query = self.build_query(*from_coords, *to_coords, date, time, arrive_by)
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.url, json={"query": query})
                response.raise_for_status()
                data = response.json()
                
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
                            "route": leg["route"]["shortName"] if leg["route"] else None
                        })
                    
                    processed_results.append({
                        "summary": {
                            "duration_minutes": self.format_duration(plan["duration"]),
                            "start_time": self.format_time(plan["startTime"]),
                            "end_time": self.format_time(plan["endTime"])
                        },
                        "mode_breakdown": mode_breakdown,
                        "detailed_legs": detailed_legs
                    })
                
                # Sort by end time (arrival) to find the best options
                processed_results.sort(key=lambda x: x["summary"]["end_time"])
                return processed_results
            except Exception as e:
                return {"error": str(e)}

    # For backward compatibility with cli.py if not updated yet
    async def get_fastest_route(self, *args, **kwargs):
        results = await self.get_itineraries(*args, **kwargs)
        if isinstance(results, list):
            return results[0]
        return results
