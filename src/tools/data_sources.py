from __future__ import annotations
import os
import random
from typing import Dict, Tuple
import httpx


def get_mock_kpi_values(kpi_id: str) -> Tuple[float, float]:
    random.seed(hash(kpi_id) % 100000)
    v1 = random.randint(5, 30)
    v2 = max(0, v1 + random.randint(-2, 2))
    return float(v1), float(v2)


async def get_real_kpi_value_example(team_id: int = 81) -> Dict:
    """
    Real API hook example (football-data.org).
    You can replace with player-level providers later.
    """
    api_key = os.getenv("FOOTBALL_DATA_API_KEY", "")
    base_url = os.getenv("FOOTBALL_DATA_BASE_URL", "https://api.football-data.org/v4")
    if not api_key:
        return {"enabled": False, "reason": "Missing FOOTBALL_DATA_API_KEY"}

    headers = {"X-Auth-Token": api_key}
    url = f"{base_url}/teams/{team_id}/matches?status=FINISHED&limit=5"

    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        return {"enabled": True, "data": r.json()}