import asyncio
from datetime import datetime, timezone

import pytest

from fake_ha import FakeHomeAssistant
from ha_client import HAClient, normalize_history, parse_timestamp


def test_parse_timestamp_formats():
    expected = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
    assert parse_timestamp("2026-09-27T10:00:00+00:00") == expected
    assert parse_timestamp(expected.timestamp()) == expected
    assert parse_timestamp("kaputt") is None
    assert parse_timestamp(None) is None


def test_normalize_compressed_history_carries_attributes():
    entries = [
        {"s": "1", "a": {"temp": 20}, "lu": 100.0},
        {"s": "2", "lu": 160.0, "lc": 150.0},
    ]
    result = normalize_history(entries)
    assert result[0]["attributes"] == {"temp": 20}
    assert result[1]["attributes"] == {"temp": 20}
    assert result[0]["last_changed"] == result[0]["last_updated"]
    assert result[1]["last_changed"].timestamp() == 150.0


@pytest.fixture
async def fake_ha(unused_tcp_port):
    ha = FakeHomeAssistant(states=[{"entity_id": "sensor.pv", "state": "5", "attributes": {},
                                    "last_changed": "2026-09-27T10:00:00+00:00",
                                    "last_updated": "2026-09-27T10:00:00+00:00"}],
                           history={"sensor.pv": [{"s": "4", "a": {}, "lu": 1790000000.0}]})
    await ha.start(unused_tcp_port)
    yield ha
    await ha.stop()


async def test_connects_loads_states_subscribes_and_dispatches(fake_ha):
    received = []
    connected = asyncio.Event()

    async def on_connected():
        connected.set()

    client = HAClient(fake_ha.url, "geheim", received.append, on_connected)
    task = asyncio.create_task(client.run())
    try:
        await asyncio.wait_for(connected.wait(), 5)
        assert client.connected
        assert client.states["sensor.pv"]["state"] == "5"
        await fake_ha.send_state({"entity_id": "sensor.pv", "state": "6", "attributes": {}})
        for _ in range(50):
            if received:
                break
            await asyncio.sleep(0.02)
        assert received[0]["state"] == "6"
        assert client.states["sensor.pv"]["state"] == "6"

        history = await client.history(["sensor.pv"], datetime.now(timezone.utc), datetime.now(timezone.utc))
        assert history["sensor.pv"][0]["state"] == "4"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_reconnects_after_drop(fake_ha):
    connects = 0
    connected = asyncio.Event()

    async def on_connected():
        nonlocal connects
        connects += 1
        connected.set()

    client = HAClient(fake_ha.url, "geheim", lambda _state: None, on_connected)
    task = asyncio.create_task(client.run())
    try:
        await asyncio.wait_for(connected.wait(), 5)
        connected.clear()
        await fake_ha.drop_connections()
        await asyncio.wait_for(connected.wait(), 5)
        assert connects == 2
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_wrong_token_is_reported(fake_ha):
    client = HAClient(fake_ha.url, "falsch", lambda _state: None, lambda: asyncio.sleep(0))
    task = asyncio.create_task(client.run())
    try:
        for _ in range(100):
            if client.last_error:
                break
            await asyncio.sleep(0.02)
        assert not client.connected
        assert "abgelehnt" in client.last_error
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
