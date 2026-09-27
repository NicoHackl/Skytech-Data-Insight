"""Zugriff auf die HTTP-API von Grafana im Container.

Angemeldet wird über den Auth-Proxy (D-006): Grafana vertraut dem Header
`X-WEBAUTH-USER` nur von 127.0.0.1, also nur Prozessen im Container. Der
Benutzer `skytech-mcp` wird beim ersten Aufruf automatisch angelegt.
"""

import asyncio
import os
from typing import Any

import aiohttp

GRAFANA_BASE_URL = "http://127.0.0.1:3001"
AUTH_USER = "skytech-mcp"
TIMEOUT_S = 30


class GrafanaError(RuntimeError):
    pass


class GrafanaClient:
    def __init__(self, session: aiohttp.ClientSession, ingress_entry: str | None = None,
                 base_url: str = GRAFANA_BASE_URL) -> None:
        entry = os.environ.get("SKYTECH_INGRESS_ENTRY", "") if ingress_entry is None else ingress_entry
        self._api = f"{base_url}{entry}/grafana/api"
        self._session = session

    async def _request(self, method: str, path: str, payload: Any = None) -> Any:
        try:
            async with self._session.request(
                method, f"{self._api}{path}", json=payload,
                headers={"X-WEBAUTH-USER": AUTH_USER},
                timeout=aiohttp.ClientTimeout(total=TIMEOUT_S),
            ) as response:
                body = await response.json(content_type=None)
                if response.status >= 400:
                    message = body.get("message") if isinstance(body, dict) else None
                    raise GrafanaError(f"Grafana antwortet {response.status}: {message or body}")
                return body
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise GrafanaError(f"Grafana nicht erreichbar (startet eventuell gerade): {exc}") from exc

    async def datasources(self) -> list[dict]:
        return await self._request("GET", "/datasources")

    async def search_dashboards(self, query: str = "") -> list[dict]:
        return await self._request("GET", f"/search?type=dash-db&query={aiohttp.helpers.quote(query)}")

    async def folders(self) -> list[dict]:
        return await self._request("GET", "/folders")

    async def ensure_folder(self, title: str) -> str:
        """uid eines Ordners mit diesem Titel; legt ihn bei Bedarf an."""
        for folder in await self.folders():
            if folder.get("title") == title:
                return folder["uid"]
        created = await self._request("POST", "/folders", {"title": title})
        return created["uid"]

    async def dashboard(self, uid: str) -> dict:
        return await self._request("GET", f"/dashboards/uid/{uid}")

    async def save_dashboard(self, dashboard: dict, folder_uid: str | None, message: str) -> dict:
        payload = {"dashboard": dashboard, "overwrite": True, "message": message}
        if folder_uid:
            payload["folderUid"] = folder_uid
        return await self._request("POST", "/dashboards/db", payload)

    async def delete_dashboard(self, uid: str) -> dict:
        return await self._request("DELETE", f"/dashboards/uid/{uid}")
