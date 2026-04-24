import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from nsw_commute.client import OTPClient
from datetime import datetime

@pytest.mark.asyncio
async def test_client_query_structure():
    client = OTPClient(base_url="http://localhost:8080")
    query = client.build_query((-33.8688, 151.2093), "1:200060", "2026-04-06", "08:30:00", arriveBy=True)
    assert "plan" in query
    assert 'fromPlace: "-33.8688, 151.2093"' in query
    assert 'toPlace: "1:200060"' in query
    assert "arriveBy: true" in query
    assert "interlineWithPreviousLeg" in query

@pytest.mark.asyncio
async def test_get_itineraries_formatting():
    client = OTPClient()
    mock_data = {
        "data": {
            "plan": {
                "itineraries": [
                    {
                        "duration": 1500,
                        "startTime": 1775424240000,
                        "endTime": 1775425740000,
                        "legs": [
                            {
                                "mode": "WALK",
                                "duration": 300,
                                "startTime": 1775424240000,
                                "endTime": 1775424540000,
                                "from": {"name": "Origin"},
                                "to": {"name": "Station"},
                                "route": None,
                                "interlineWithPreviousLeg": False
                            },
                            {
                                "mode": "RAIL",
                                "duration": 1200,
                                "startTime": 1775424540000,
                                "endTime": 1775425740000,
                                "from": {"name": "Station"},
                                "to": {"name": "Destination"},
                                "route": {"shortName": "T1", "longName": "North Shore & Western"},
                                "interlineWithPreviousLeg": False
                            }
                        ]
                    }
                ]
            }
        }
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        
        results = await client.get_itineraries((-33.8, 151.2), "1:200060", "2026-04-06", "08:30")
        assert len(results) == 1
        result = results[0]
        assert result["summary"]["duration_minutes"] == 25.0
        assert result["mode_breakdown"]["WALK"] == 5.0
        assert result["mode_breakdown"]["RAIL"] == 20.0

@pytest.mark.asyncio
async def test_search_stations_mode_filtering():
    client = OTPClient()
    mock_data = {
        "data": {
            "stops": [
                {
                    "gtfsId": "1:200812",
                    "name": "Railway Square",
                    "lat": -33.8836,
                    "lon": 151.2035,
                    "locationType": "STATION",
                    "stops": [{"vehicleMode": "BUS"}],
                    "parentStation": None
                },
                {
                    "gtfsId": "1:200060",
                    "name": "Central Station",
                    "lat": -33.8840,
                    "lon": 151.2062,
                    "locationType": "STATION",
                    "stops": [{"vehicleMode": "RAIL"}],
                    "parentStation": None
                }
            ]
        }
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        
        results = await client.search_stations("Central")
        assert len(results) == 1
        assert results[0]["name"] == "Central Station"
        assert results[0]["id"] == "1:200060"

@pytest.mark.asyncio
async def test_list_stations_filtering():
    client = OTPClient()
    mock_data = {
        "data": {
            "stations": [
                {
                    "gtfsId": "1:1",
                    "name": "Train Station",
                    "lat": -33.8,
                    "lon": 151.2,
                    "stops": [{"vehicleMode": "RAIL"}]
                },
                {
                    "gtfsId": "1:2",
                    "name": "Bus Stop Hub",
                    "lat": -33.9,
                    "lon": 151.3,
                    "stops": [{"vehicleMode": "BUS"}]
                }
            ]
        }
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        
        results = await client.list_stations()
        assert len(results) == 1
        assert results[0]["name"] == "Train Station"
