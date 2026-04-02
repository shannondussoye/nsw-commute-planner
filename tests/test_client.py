import pytest
from nsw_commute.client import OTPClient

@pytest.mark.asyncio
async def test_client_query_structure():
    client = OTPClient(base_url="http://localhost:8080")
    # This will fail because the server isn't running in CI, 
    # but we test the query generation logic.
    query = client.build_query(-33.8688, 151.2093, -33.8915, 151.2017, "2026-04-06", "08:30:00")
    assert "plan" in query
    assert "from" in query  # Adjusted based on actual client code
    assert "to" in query    # Adjusted based on actual client code
