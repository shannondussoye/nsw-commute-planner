import asyncio
import json
import argparse
import sys
from nsw_commute.client import OTPClient

async def main():
    parser = argparse.ArgumentParser(description="NSW Local Commute Calculator")
    
    # Discovery Options (Exclusive)
    parser.add_argument("--search", type=str, help="Search for Station ID by name")
    parser.add_argument("--list", action="store_true", help="List all Parent Stations (Trains and Metro)")
    
    # Origin Options
    parser.add_argument("--from-lat", type=float, help="Origin latitude")
    parser.add_argument("--from-lon", type=float, help="Origin longitude")
    parser.add_argument("--from-id", type=str, help="Origin Station/Stop ID")
    
    # Destination Options
    parser.add_argument("--to-lat", type=float, help="Destination latitude")
    parser.add_argument("--to-lon", type=float, help="Destination longitude")
    parser.add_argument("--to-id", type=str, help="Destination Station/Stop ID")
    
    # Timing
    parser.add_argument("--date", type=str, help="Date in YYYY-MM-DD format")
    parser.add_argument("--time", type=str, help="Time in HH:mm format")
    parser.add_argument("--arrive-by", action="store_true", help="Set to search for arrival time")

    args = parser.parse_args()
    client = OTPClient()

    # Handle List Mode
    if args.list:
        results = await client.list_stations()
        print(json.dumps(results, indent=2))
        return

    # Handle Search Mode
    if args.search:
        results = await client.search_stations(args.search)
        print(json.dumps(results, indent=2))
        return

    # Standard Commute Mode - Check Requirements
    if not (args.date and args.time):
        print("Error: --date and --time are required for commute calculation")
        sys.exit(1)

    # Determine Origin
    if args.from_id:
        origin = args.from_id
    elif args.from_lat and args.from_lon:
        origin = (args.from_lat, args.from_lon)
    else:
        print("Error: Must provide --list, --search, or --from-id/coords")
        sys.exit(1)

    # Determine Destination
    if args.to_id:
        destination = args.to_id
    elif args.to_lat and args.to_lon:
        destination = (args.to_lat, args.to_lon)
    else:
        print("Error: Must provide --list, --search, or --to-id/coords")
        sys.exit(1)

    # Run the query
    results = await client.get_itineraries(
        origin,
        destination,
        args.date,
        args.time,
        args.arrive_by
    )
    
    # Output the single best itinerary as formatted JSON
    if isinstance(results, list) and len(results) > 0:
        print(json.dumps(results[0], indent=2))
    else:
        print(json.dumps(results, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
