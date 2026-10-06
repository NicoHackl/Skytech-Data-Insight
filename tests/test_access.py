"""Zugänge (D-025): Supervisor-Client, Zusammenführen der Optionen, Anwenden
ohne Secret in Kommandozeile oder Log, API-Verhalten."""

import asyncio
import logging

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import access_service
import main
from supervisor_client import SupervisorClient, SupervisorPermissionDenied

OPTIONS = {"log_level": "info", "grafana_admin_password": "", "db_password": "alt-geheim",
           "db_readonly_password": "", "mcp_token": "kurz"}


def fake_supervisor_app(state: dict) -> web.Application:
    async def info(request):
        if request.headers.get("Authorization") != "Bearer tok":
            return web.json_response({"result": "error", "message": "unauthorized"}, status=401)
        return web.json_response({"result": "ok", "data": {
            "options": state["options"], "network": {"5432/tcp": 5432, "3000/tcp": None, "8765/tcp": 8765}}})

    async def network(_request):
        return web.json_response({"result": "ok", "data": {"interfaces": [
            {"primary": False, "ipv4": {"address": ["10.0.0.2/24"]}},
            {"primary": True, "ipv4": {"address": ["192.168.1.20/24"]}}]}})

    async def validate(request):
        state["validated"] = await request.json()
        return web.json_response({"result": "ok", "data": {"valid": True}})

    async def save(request):
        if state.get("forbidden"):
            return web.json_response({"result": "error", "message": "forbidden"}, status=403)
        state["options"] = (await request.json())["options"]
        return web.json_response({"result": "ok", "data": {}})

    app = web.Application()
    app.router.add_get("/addons/self/info", info)
    app.router.add_get("/network/info", network)
    app.router.add_post("/addons/self/options/validate", validate)
    app.router.add_post("/addons/self/options", save)
    return app


@pytest.fixture
async def supervisor():
    state = {"options": dict(OPTIONS)}
    server = TestServer(fake_supervisor_app(state))
    await server.start_server()
    async with aiohttp.ClientSession() as session:
        yield SupervisorClient(session, token="tok", base_url=str(server.make_url(""))), state
    await server.close()


@pytest.fixture
def commands(monkeypatch):
    """Ersetzt Unterprozesse; merkt Kommando, Umgebung und Eingabe."""
    calls = []

    class Process:
        returncode = 0

        async def communicate(self, data=None):
            calls[-1]["stdin"] = data
            return b"", b""

    async def fake_exec(*command, env=None, **_kwargs):
        calls.append({"command": list(command), "env": env or {}})
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return calls, Process


def test_primary_address_and_mcp_minimum():
    assert access_service.primary_address({"interfaces": [{"primary": True, "ipv4": {"address": ["192.168.1.5/24"]}}]}) == "192.168.1.5"
    assert access_service.primary_address({"interfaces": []}) is None
    mcp = access_service.BY_KEY["mcp"]
    assert not access_service.is_set(mcp, "kurz") and access_service.is_set(mcp, "x" * 16)
    assert len(access_service.new_secret()) == 32


async def test_overview_reports_status_ports_and_host(supervisor):
    client, _ = supervisor
    result = await access_service.overview(client)
    by_key = {item["schluessel"]: item for item in result["zugaenge"]}
    assert result["host"] == "192.168.1.20"
    assert by_key["datenbank"]["gesetzt"] is True and by_key["datenbank_lesen"]["gesetzt"] is False
    assert by_key["mcp"]["gesetzt"] is False  # zu kurz – Dienst bleibt aus
    assert by_key["grafana"]["port"] is None and by_key["mcp"]["port"] == 8765
    assert "alt-geheim" not in str(result)


async def test_change_merges_options_and_keeps_secret_out_of_argv(supervisor, commands, caplog):
    client, state = supervisor
    calls, _ = commands
    caplog.set_level(logging.DEBUG)
    await access_service.change(client, "datenbank_lesen", "neu-geheim-123")
    assert state["options"] == {**OPTIONS, "db_readonly_password": "neu-geheim-123"}
    assert state["validated"]["db_password"] == "alt-geheim"
    assert calls[0]["env"]["SKYTECH_ROLE"] == "skytech_reader"
    assert calls[0]["env"]["SKYTECH_PASSWORD"] == "neu-geheim-123"
    assert "neu-geheim-123" not in " ".join(calls[0]["command"])

    await access_service.change(client, "grafana", "grafana-geheim")
    assert calls[1]["stdin"] == b"grafana-geheim" and "grafana-geheim" not in " ".join(calls[1]["command"])
    await access_service.change(client, "mcp", "m" * 32)
    assert calls[2]["command"] == ["s6-svc", "-r", "/run/service/mcp"]
    assert "geheim" not in caplog.text


async def test_failed_apply_keeps_saved_value_and_hides_secret(supervisor, commands, caplog):
    client, state = supervisor
    _, process = commands
    process.returncode = 2
    with pytest.raises(access_service.AccessError, match="Neustart"):
        await access_service.change(client, "datenbank", "streng-geheim")
    assert state["options"]["db_password"] == "streng-geheim"
    assert "streng-geheim" not in caplog.text


async def test_missing_manager_role_is_explained(supervisor):
    client, state = supervisor
    state["forbidden"] = True
    with pytest.raises(SupervisorPermissionDenied, match="manager"):
        await access_service.change(client, "datenbank", "x")


async def test_access_api(supervisor, commands):
    client, state = supervisor
    service = main.AdminService(ingress_entry="", version="test", start_backend=False)
    async with TestClient(TestServer(service.build_app())) as http:
        # Ohne Supervisor (lokaler Test): lesbar, aber nicht änderbar.
        local = await (await http.get("/api/access")).json()
        assert local["verfuegbar"] is False
        assert (await http.post("/api/access/datenbank/neu", json={"bestaetigung": "datenbank"})).status == 503

        service.supervisor = client
        assert (await http.post("/api/access/gibtsnicht/neu", json={"bestaetigung": "gibtsnicht"})).status == 404
        assert (await http.post("/api/access/datenbank/neu", json={})).status == 400

        response = await http.post("/api/access/datenbank/neu", json={"bestaetigung": "datenbank"})
        body = await response.json()
        assert response.status == 200 and response.headers["Cache-Control"] == "no-store"
        assert len(body["secret"]) == 32 and state["options"]["db_password"] == body["secret"]

        locked = await (await http.post("/api/access/mcp/sperren", json={"bestaetigung": "mcp"})).json()
        assert locked["secret"] is None and state["options"]["mcp_token"] == ""

        _, process = commands
        process.returncode = 1
        warned = await (await http.post("/api/access/grafana/neu", json={"bestaetigung": "grafana"})).json()
        assert warned["secret"] and "Neustart" in warned["warnung"]


async def test_missing_program_still_reports_saved_secret(supervisor, monkeypatch):
    client, state = supervisor

    async def missing(*_command, **_kwargs):
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", missing)
    with pytest.raises(access_service.AccessError, match="Neustart"):
        await access_service.change(client, "datenbank_lesen", "x-geheim")
    assert state["options"]["db_readonly_password"] == "x-geheim"
