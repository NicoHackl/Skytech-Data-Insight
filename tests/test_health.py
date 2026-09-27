import asyncio

import aiohttp
import pytest
from aiohttp import web

import health


def test_database_ok_shows_both_versions():
    result = health.describe_database("17.11 (Debian 17.11-1.pgdg12+2)", "2.30.1")
    assert result.is_ok
    assert result.detail == "PostgreSQL 17.11 · TimescaleDB 2.30.1"


def test_database_without_timescale_is_not_ok():
    result = health.describe_database("17.11", None)
    assert not result.is_ok
    assert "TimescaleDB fehlt" in result.detail


@pytest.mark.parametrize("payload", [None, [], "ok"])
def test_grafana_invalid_payload(payload):
    assert not health.describe_grafana(payload).is_ok


def test_grafana_healthy():
    result = health.describe_grafana({"database": "ok", "version": "13.2.2"})
    assert result.is_ok
    assert result.detail == "Version 13.2.2"


def test_grafana_database_failing():
    assert not health.describe_grafana({"database": "failing", "version": "13.2.2"}).is_ok


async def test_collect_keeps_order():
    async def slow():
        await asyncio.sleep(0.02)
        return health.ServiceHealth("a", "A", True, "")

    async def fast():
        return health.ServiceHealth("b", "B", True, "")

    result = await health.collect([slow, fast])
    assert [service.key for service in result] == ["a", "b"]


async def test_probe_grafana_uses_ingress_sub_path(monkeypatch, unused_tcp_port):
    seen = []

    async def handler(request):
        seen.append(request.path)
        return web.json_response({"database": "ok", "version": "13.2.2"})

    app = web.Application()
    app.router.add_get("/{tail:.*}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", unused_tcp_port).start()
    monkeypatch.setattr(health, "GRAFANA_BASE_URL", f"http://127.0.0.1:{unused_tcp_port}")
    try:
        async with aiohttp.ClientSession() as session:
            result = await health.probe_grafana(session, "/api/hassio_ingress/abc")
    finally:
        await runner.cleanup()
    assert result.is_ok
    assert seen == ["/api/hassio_ingress/abc/grafana/api/health"]


async def test_probe_grafana_unreachable(monkeypatch, unused_tcp_port):
    monkeypatch.setattr(health, "GRAFANA_BASE_URL", f"http://127.0.0.1:{unused_tcp_port}")
    async with aiohttp.ClientSession() as session:
        result = await health.probe_grafana(session, "")
    assert not result.is_ok
    assert result.detail == "Nicht erreichbar"
