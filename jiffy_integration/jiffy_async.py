import aiohttp
import json
import logging
from django.conf import settings

logger = logging.getLogger("my-logger")


class AsyncJiffyClient:
    def __init__(self, token_getter, token_refresher):
        self.base_url = "https://api.jiffy.world"
        self.token_getter = token_getter
        self.token_refresher = token_refresher

    async def request(
        self,
        session: aiohttp.ClientSession,
        method: str,
        action: str,
        payload=None,
        retry_count=0,
        max_retries=2,
        is_token_required=True,
    ):
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        if is_token_required:
            token = self.token_getter()
            if token:
                headers["Authorization"] = f"Bearer {token.strip()}"

        url = f"{self.base_url}{action}"

        async with session.request(
            method,
            url,
            headers=headers,
            data=json.dumps(payload) if payload else None,
            timeout=aiohttp.ClientTimeout(total=40),
        ) as resp:
            try:
                res_json = await resp.json()
            except Exception:
                text = await resp.text()
                logger.error("Non JSON response: %s", text[:300])
                return {"success": False, "error": "Non JSON response"}

        if resp.status in (401, 403) and retry_count < max_retries:
            await self.token_refresher()
            return await self.request(
                session,
                method,
                action,
                payload,
                retry_count + 1,
                max_retries,
                is_token_required,
            )

        return res_json
