"""MCP-Server über HTTP: Anmeldung, Werkzeugliste, Werkzeugaufruf, Fehlerweitergabe."""

import asyncio
import json

import aiohttp
import pytest
import uvicorn

import mcp_server
from mcp_tools import ToolError

TOKEN = "test-token-1234567890"


class FakeTools:
    def __init__(self):
        self.calls = []

    async def query(self, sql, max_rows=500):
        self.calls.append(("query", sql, max_rows))
        return {"spalten": ["x"], "zeilen": [[1]], "anzahl": 1, "abgeschnitten": False}

    async def execute(self, sql, reason):
        raise ToolError("absichtlich fehlgeschlagen")

    def list_backups(self):
        return []


@pytest.fixture
async def server_url(unused_tcp_port):
    tools = FakeTools()
    config = uvicorn.Config(mcp_server.build_app(tools, TOKEN), host="127.0.0.1", port=unused_tcp_port,
                            log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.02)
    yield f"http://127.0.0.1:{unused_tcp_port}/mcp", tools
    server.should_exit = True
    await task


async def rpc(url, method, params=None, token=TOKEN, request_id=1):
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
               "MCP-Protocol-Version": "2025-06-18"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=body, headers=headers) as response:
            text = await response.text()
            return response.status, (json.loads(text) if text else None)


async def test_rejects_missing_or_wrong_token(server_url):
    url, _ = server_url
    status, _ = await rpc(url, "tools/list", token=None)
    assert status == 401
    status, _ = await rpc(url, "tools/list", token="falsch")
    assert status == 401


async def test_initialize_and_list_tools(server_url):
    url, _ = server_url
    status, body = await rpc(url, "initialize", {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"}})
    assert status == 200, body
    assert body["result"]["serverInfo"]["name"] == "Skytech Data Insight"
    assert "skytech-db" in body["result"]["instructions"]
    status, body = await rpc(url, "tools/list", request_id=2)
    names = {tool["name"] for tool in body["result"]["tools"]}
    assert {"sql_abfrage", "sql_ausfuehren", "migration_anlegen", "grafana_dashboard_speichern",
            "sensoren_anlegen", "backup_erstellen"} <= names
    readonly = {tool["name"]: tool.get("annotations", {}).get("readOnlyHint") for tool in body["result"]["tools"]}
    assert readonly["sql_abfrage"] is True and readonly["sql_ausfuehren"] is False


async def test_tool_call_and_error_text(server_url):
    url, tools = server_url
    status, body = await rpc(url, "tools/call", {"name": "sql_abfrage", "arguments": {"sql": "SELECT 1", "max_zeilen": 5}})
    assert status == 200, body
    assert json.loads(body["result"]["content"][0]["text"])["zeilen"] == [[1]]
    assert tools.calls == [("query", "SELECT 1", 5)]
    status, body = await rpc(url, "tools/call", {"name": "sql_ausfuehren", "arguments": {"sql": "x", "begruendung": "y"}})
    assert json.loads(body["result"]["content"][0]["text"]) == {"fehler": "absichtlich fehlgeschlagen"}
