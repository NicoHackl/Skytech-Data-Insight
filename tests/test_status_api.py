from aiohttp.test_utils import TestClient, TestServer

import health
import main


async def test_status_reports_services_in_order(monkeypatch):
    async def database():
        return health.ServiceHealth("database", "Datenbank", True, "PostgreSQL 17.11 · TimescaleDB 2.30.1")

    async def grafana(_session, ingress_entry):
        return health.ServiceHealth("grafana", "Grafana", False, f"Pfad {ingress_entry}")

    monkeypatch.setattr(health, "probe_database", database)
    monkeypatch.setattr(health, "probe_grafana", grafana)

    service = main.AdminService(ingress_entry="/api/hassio_ingress/abc", version="0.1.0")
    async with TestClient(TestServer(service.build_app())) as client:
        response = await client.get("/api/status")
        assert response.status == 200
        body = await response.json()

    assert body["version"] == "0.1.0"
    assert [s["key"] for s in body["services"]] == ["database", "grafana"]
    assert body["services"][1]["detail"] == "Pfad /api/hassio_ingress/abc"
    # Menschenlesbar ohne Offset (Regel 9), Maschinenformat zusätzlich.
    assert "+" not in body["checked_at"] and len(body["checked_at"]) == 19
    assert body["checked_at_iso"].endswith("+00:00")
