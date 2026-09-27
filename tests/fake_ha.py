"""Nachbau der HA-WebSocket-API für Tests: Anmeldung, get_states, Abo, Verlauf."""

import asyncio

from aiohttp import web


class FakeHomeAssistant:
    def __init__(self, token="geheim", states=None, history=None):
        self.token = token
        self.states = states or []
        self.history = history or {}
        self.connections: list[web.WebSocketResponse] = []
        self.commands: list[dict] = []
        self.subscription_id = None
        self.subscribed = asyncio.Event()
        self._runner = None
        self.port = None

    async def start(self, port):
        app = web.Application()
        app.router.add_get("/api/websocket", self._handle)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        await web.TCPSite(self._runner, "127.0.0.1", port).start()
        self.port = port

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}/api/websocket"

    async def stop(self):
        for websocket in self.connections:
            await websocket.close()
        await self._runner.cleanup()

    async def drop_connections(self):
        for websocket in list(self.connections):
            await websocket.close()
        self.connections.clear()
        self.subscribed.clear()

    async def send_state(self, new_state):
        for websocket in list(self.connections):
            if websocket.closed:
                self.connections.remove(websocket)
                continue
            await websocket.send_json({
                "id": self.subscription_id,
                "type": "event",
                "event": {"event_type": "state_changed",
                          "data": {"entity_id": new_state["entity_id"], "new_state": new_state}},
            })

    async def _handle(self, request):
        websocket = web.WebSocketResponse()
        await websocket.prepare(request)
        await websocket.send_json({"type": "auth_required"})
        auth = await websocket.receive_json()
        if auth.get("access_token") != self.token:
            await websocket.send_json({"type": "auth_invalid"})
            await websocket.close()
            return websocket
        await websocket.send_json({"type": "auth_ok"})
        self.connections.append(websocket)
        async for message in websocket:
            command = message.json()
            self.commands.append(command)
            kind = command["type"]
            if kind == "get_states":
                result = self.states
            elif kind == "subscribe_events":
                self.subscription_id = command["id"]
                result = None
            elif kind == "history/history_during_period":
                result = {e: self.history.get(e, []) for e in command["entity_ids"]}
            else:
                await websocket.send_json({"id": command["id"], "type": "result", "success": False,
                                           "error": {"code": "unknown_command", "message": "Unbekannt"}})
                continue
            await websocket.send_json({"id": command["id"], "type": "result", "success": True, "result": result})
            if kind == "subscribe_events":
                self.subscribed.set()
        return websocket
