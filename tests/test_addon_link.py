"""Tests für den Link im Sidebar-Fuß auf die HA-Konfigurationsseite (D-028)."""

from aiohttp.test_utils import TestClient, TestServer

import addon_link
import main
from supervisor_client import SupervisorRejected, SupervisorUnavailable


class InfoSupervisor:
    """Liefert `/addons/self/info`; zählt die Aufrufe."""

    def __init__(self, info=None, *, available=True, fehler=None):
        self.info = info or {}
        self.available = available
        self.fehler = fehler
        self.calls = 0

    async def self_info(self):
        self.calls += 1
        if self.fehler:
            raise self.fehler
        return dict(self.info)


INFO = {"slug": "e778e1d3_skytech_data_insight", "name": "Skytech Data Insight"}


async def test_link_nutzt_slug_mit_repository_praefix_und_namen_vom_supervisor():
    assert await addon_link.fetch(InfoSupervisor(INFO)) == {
        "name": "Skytech Data Insight",
        "config_path": "/hassio/addon/e778e1d3_skytech_data_insight/config",
    }


async def test_ohne_supervisor_gibt_es_keinen_link():
    assert await addon_link.fetch(InfoSupervisor(available=False)) is None


async def test_supervisor_fehler_liefert_keinen_link():
    for fehler in (SupervisorUnavailable("weg"), SupervisorRejected("HTTP 500")):
        assert await addon_link.fetch(InfoSupervisor(fehler=fehler)) is None


async def test_ungueltiger_slug_wird_nicht_zum_pfad():
    assert await addon_link.fetch(InfoSupervisor({"slug": "../../evil"})) is None


async def test_endpunkt_merkt_nur_den_erfolg():
    service = main.AdminService(ingress_entry="/api/hassio_ingress/abc", version="0.1.0", start_backend=False)
    async with TestClient(TestServer(service.build_app())) as client:
        sup = InfoSupervisor(fehler=SupervisorUnavailable("weg"))
        service.supervisor = sup
        response = await client.get("/api/addon")
        assert response.status == 200
        assert await response.json() == {"name": "Skytech Data Insight", "config_path": None}

        sup.fehler = None
        sup.info = INFO
        body = await (await client.get("/api/addon")).json()
        assert body["config_path"] == "/hassio/addon/e778e1d3_skytech_data_insight/config"
        await client.get("/api/addon")
        assert sup.calls == 2
