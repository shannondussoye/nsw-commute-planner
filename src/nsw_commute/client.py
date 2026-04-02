import httpx
import asyncio

class OTPClient:
    def __init__(self, base_url="http://localhost:8080"):
        self.url = f"{base_url}/otp/routers/default/index/graphql"

    def build_query(self, from_lat, from_lon, to_lat, to_lon, date, time):
        # Adjusted GraphQL query to match OTP 2.x schema
        # Note: 'fromPlace' and 'toPlace' are common in OTP queries.
        return f"""
        {{
          plan(
            from: {{ lat: {from_lat}, lon: {from_lon} }}
            to: {{ lat: {to_lat}, lon: {to_lon} }}
            date: "{date}"
            time: "{time}"
            transportModes: [{{ mode: TRANSIT }}, {{ mode: WALK }}]
          ) {{
            itineraries {{
              duration
              startTime
              endTime
            }}
          }}
        }}
        """

    async def get_fastest_route(self, from_coords, to_coords, date, time):
        query = self.build_query(*from_coords, *to_coords, date, time)
        async with httpx.AsyncClient() as client:
            response = await client.post(self.url, json={"query": query})
            data = response.json()
            if not data.get("data", {}).get("plan", {}).get("itineraries"):
                return {"error": "no_route_found"}
            
            # Return fastest duration
            itineraries = data["data"]["plan"]["itineraries"]
            fastest = min(itineraries, key=lambda x: x["duration"])
            return {
                "duration_seconds": fastest["duration"],
                "start": fastest["startTime"],
                "end": fastest["endTime"]
            }
