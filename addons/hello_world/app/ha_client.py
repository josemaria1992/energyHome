from __future__ import annotations

from typing import Optional

import httpx


async def fetch_entity_state(ha_url: str, token: str, entity_id: str) -> Optional[float]:
    url = f"{ha_url.rstrip('/')}/api/states/{entity_id}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
    state = str(data.get("state", ""))
    if state in {"unknown", "unavailable", "None", ""}:
        return None
    try:
        return float(state)
    except ValueError:
        return None
