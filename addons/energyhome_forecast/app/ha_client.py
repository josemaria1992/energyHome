from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger("energyhome")


class HAClient:
    def __init__(self, ha_url: str, token: str) -> None:
        self.ha_url = ha_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        self.client = httpx.AsyncClient(timeout=10.0)

    async def close(self) -> None:
        await self.client.aclose()

    async def fetch_entity_state(self, entity_id: str) -> Optional[float]:
        url = f"{self.ha_url}/api/states/{entity_id}"
        for attempt, delay in enumerate([0.0, 0.2, 0.5, 1.0], start=1):
            if delay:
                await asyncio.sleep(delay)
            try:
                response = await self.client.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                state = str(data.get("state", ""))
                if state in {"unknown", "unavailable", "None", ""}:
                    return None
                try:
                    return float(state)
                except ValueError:
                    logger.warning("Failed to parse state for %s: %s", entity_id, state)
                    return None
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                if attempt == 4:
                    raise
                logger.warning("HA request failed for %s (attempt %s): %s", entity_id, attempt, exc)
        return None
