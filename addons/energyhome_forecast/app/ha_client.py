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

    async def validate_auth(self) -> None:
        """Startup self-check to validate HA auth before starting poll loop."""
        url = f"{self.ha_url}/api/config"
        try:
            response = await self.client.get(url, headers=self.headers)
            if response.status_code in {401, 403}:
                logger.error("HA auth failed: received %d from %s", response.status_code, url)
                raise ValueError(
                    f"HA authentication failed ({response.status_code}). "
                    "Check ha_token in configuration or verify SUPERVISOR_TOKEN is available."
                )
            response.raise_for_status()
            logger.info("HA auth validated successfully (200 OK from /api/config)")
        except httpx.RequestError as exc:
            logger.error("Failed to connect to HA during auth validation: %s", exc)
            raise ValueError(f"Cannot connect to Home Assistant at {self.ha_url}: {exc}") from exc

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
            except httpx.HTTPStatusError as exc:
                # 404 means entity doesn't exist - don't retry, just log once and return None
                if exc.response.status_code == 404:
                    logger.warning("Entity %s not found in HA (404). Disabling it.", entity_id)
                    return None
                # 401/403 means auth issue - don't retry
                if exc.response.status_code in {401, 403}:
                    logger.error("Entity %s: auth failed (%d). Check ha_token.", entity_id, exc.response.status_code)
                    return None
                # For other HTTP errors (5xx), retry
                if attempt == 4:
                    raise
                logger.warning("HA request failed for %s (attempt %s): %s", entity_id, attempt, exc)
                continue
            except httpx.RequestError as exc:
                # Network/timeout errors - retry
                if attempt == 4:
                    raise
                logger.warning("HA request failed for %s (attempt %s): %s", entity_id, attempt, exc)
                continue
