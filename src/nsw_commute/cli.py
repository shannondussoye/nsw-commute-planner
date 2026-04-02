import asyncio
import json
import sys
from nsw_commute.client import OTPClient

async def main():
    client = OTPClient()
    # Example: Run multiple queries in parallel
    tasks = [
        client.get_fastest_route((-33.8688, 151.2093), (-33.8915, 151.2017), "2026-04-06", "08:00:00"),
        client.get_fastest_route((-33.8688, 151.2093), (-33.9173, 151.2253), "2026-04-06", "08:15:00")
    ]
    results = await asyncio.gather(*tasks)
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
