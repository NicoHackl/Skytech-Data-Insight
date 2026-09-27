"""Integrationstests gegen eine echte TimescaleDB.

Laufen nur, wenn SKYTECH_TEST_DSN auf einen Superuser zeigt, z. B.
`postgresql://postgres:test@127.0.0.1:15432/postgres` (docs/test-strategie.md).
Jeder Lauf legt die Datenbank `skytech_test` neu an. Rollen werden per
`server_settings.role` gesetzt, damit die Rechte der echten Rollen gelten.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio

import minute_values
import migration_runner
import sensor_service
from collector import Collector
from fake_ha import FakeHomeAssistant
from ha_client import HAClient

DSN = os.environ.get("SKYTECH_TEST_DSN")
TEST_DB = "skytech_test"
ROLES = ("skytech_app", "skytech_collector", "skytech_admin", "skytech_reader")
T0 = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)

pytestmark = [
    pytest.mark.skipif(not DSN, reason="SKYTECH_TEST_DSN nicht gesetzt – keine TimescaleDB für Integrationstests"),
    pytest.mark.asyncio(loop_scope="module"),
]


def _test_dsn() -> str:
    base, _, _ = DSN.rpartition("/")
    return f"{base}/{TEST_DB}"


async def _pool(role: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(_test_dsn(), min_size=1, max_size=4,
                                     server_settings={"role": role, "timezone": "UTC"})


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pools():
    admin = await asyncpg.connect(DSN)
    try:
        for role in ROLES:
            exists = await admin.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", role)
            if not exists:
                await admin.execute(f"CREATE ROLE {role} LOGIN")
        await admin.execute("GRANT skytech_app TO skytech_admin")
        await admin.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        await admin.execute(f"CREATE DATABASE {TEST_DB} OWNER skytech_app")
    finally:
        await admin.close()
    superuser = await asyncpg.connect(_test_dsn())
    await superuser.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    await superuser.close()

    app_pool = await _pool("skytech_app")
    collector_pool = await _pool("skytech_collector")
    async with app_pool.acquire() as connection:
        applied = await migration_runner.migrate(connection, migration_runner.discover(site_dir=Path("/nonexistent")))
        assert [m.version for m in applied] == [1]
    yield app_pool, collector_pool
    await collector_pool.close()
    await app_pool.close()


@pytest_asyncio.fixture(loop_scope="module")
async def clean(pools):
    app_pool, _ = pools
    async with app_pool.acquire() as connection:
        await connection.execute("TRUNCATE skytech.sensor RESTART IDENTITY CASCADE")
    return pools


async def _sensor(connection, entity_id="sensor.pv_leistung", **extra):
    data = {"entity_id": entity_id, "name": entity_id, "kategorie": "pv", "groesse": "leistung", **extra}
    ids = await sensor_service.create_sensors(connection, [data], "test")
    return ids[0]


async def test_migrations_are_idempotent_and_checked(pools, tmp_path):
    app_pool, _ = pools
    async with app_pool.acquire() as connection:
        assert await migration_runner.migrate(connection, migration_runner.discover(site_dir=tmp_path)) == []
        changed = tmp_path / "sql"
        changed.mkdir()
        original = (migration_runner.SYSTEM_DIR / "0001_grundschema.sql").read_text(encoding="utf-8")
        (changed / "0001_grundschema.sql").write_text(original + "\n-- geändert\n", encoding="utf-8")
        with pytest.raises(migration_runner.MigrationError, match="verändert"):
            await migration_runner.migrate(connection, migration_runner.discover(changed, tmp_path / "leer"))


async def test_site_migration_runs_after_system(pools, tmp_path):
    app_pool, _ = pools
    (tmp_path / "0100_eigene_tabelle.sql").write_text(
        "CREATE TABLE skytech.notiz (zeit timestamptz PRIMARY KEY, text text);", encoding="utf-8")
    async with app_pool.acquire() as connection:
        applied = await migration_runner.migrate(connection, migration_runner.discover(site_dir=tmp_path))
        assert [(m.version, m.source) for m in applied] == [(100, "anlage")]
        assert await connection.fetchval("SELECT to_regclass('skytech.notiz') IS NOT NULL")


async def test_minute_values_time_weighted_with_gaps_and_counter_reset(clean):
    app_pool, collector_pool = clean
    async with app_pool.acquire() as connection:
        power = await _sensor(connection, "sensor.pv_leistung")
        energy = await _sensor(connection, "sensor.pv_energie", groesse="energie", energie_zaehler=True)
    rows = [
        (T0 - timedelta(minutes=1), power, 100.0, None),
        (T0 + timedelta(seconds=30), power, 200.0, None),
        (T0 + timedelta(minutes=1), power, None, "unavailable"),
        (T0 + timedelta(minutes=1, seconds=30), power, 300.0, None),
        (T0 - timedelta(minutes=10), energy, 10.0, None),
        (T0 + timedelta(seconds=20), energy, 12.0, None),
        (T0 + timedelta(seconds=40), energy, 13.0, None),
        (T0 + timedelta(minutes=1, seconds=10), energy, 0.5, None),
        (T0 + timedelta(minutes=2, seconds=10), energy, 1.5, None),
    ]
    async with collector_pool.acquire() as connection:
        await connection.executemany(
            "INSERT INTO skytech.messwert (zeit, sensor_id, wert, text_wert) VALUES ($1, $2, $3, $4)", rows)
        for _ in range(2):  # zweimal: Ergebnis muss gleich bleiben
            await minute_values.compute(connection, T0, T0 + timedelta(minutes=3), [power, energy])
        result = await connection.fetch(
            "SELECT sensor_id, zeit, round(mittel::numeric, 3)::float AS mittel, letzter, zuwachs, anzahl, abdeckung_s "
            "FROM skytech.messwert_1min ORDER BY sensor_id, zeit")
    got = [(r["sensor_id"], r["zeit"] - T0, r["mittel"], r["letzter"], r["zuwachs"], r["anzahl"], r["abdeckung_s"])
           for r in result]
    minute = timedelta(minutes=1)
    assert got == [
        (power, 0 * minute, 150.0, 200.0, None, 1, 60.0),
        (power, 1 * minute, 300.0, 300.0, None, 2, 30.0),
        (power, 2 * minute, 300.0, 300.0, None, 0, 60.0),
        (energy, 0 * minute, 11.667, 13.0, 3.0, 2, 60.0),
        (energy, 1 * minute, 2.583, 0.5, 0.5, 1, 60.0),
        (energy, 2 * minute, 1.333, 1.5, 1.0, 1, 60.0),
    ]


async def test_aggregates_weight_by_coverage_and_use_berlin_days(clean):
    app_pool, collector_pool = clean
    async with app_pool.acquire() as connection:
        sensor = await _sensor(connection)
    # 22:00 UTC = 00:00 Berliner Sommerzeit: gehört zum nächsten Kalendertag.
    rows = [
        (datetime(2026, 9, 27, 21, 58, tzinfo=timezone.utc), sensor, 100.0, 1, 60.0),
        (datetime(2026, 9, 27, 21, 59, tzinfo=timezone.utc), sensor, 200.0, 1, 30.0),
        (datetime(2026, 9, 27, 22, 0, tzinfo=timezone.utc), sensor, 500.0, 1, 60.0),
    ]
    async with collector_pool.acquire() as connection:
        await connection.executemany(
            "INSERT INTO skytech.messwert_1min (zeit, sensor_id, mittel, minimum, maximum, letzter, anzahl, abdeckung_s) "
            "VALUES ($1, $2, $3, $3, $3, $3, $4, $5)", rows)
    async with app_pool.acquire() as connection:
        fifteen = await connection.fetch(
            "SELECT zeit, round(mittel::numeric, 3)::float AS mittel FROM skytech.messwert_15min ORDER BY zeit")
        days = await connection.fetch(
            "SELECT zeit AT TIME ZONE 'Europe/Berlin' AS tag, mittel FROM skytech.messwert_1d ORDER BY zeit")
    assert [r["mittel"] for r in fifteen] == [133.333, 500.0]
    assert [(r["tag"].date().isoformat(), r["mittel"]) for r in days] == [
        ("2026-09-27", pytest.approx(133.333, rel=1e-4)), ("2026-09-28", 500.0)]


async def test_retention_settings(pools):
    app_pool, _ = pools
    async with app_pool.acquire() as connection:
        await connection.execute("SELECT skytech_config.aufbewahrung_anwenden()")
        jobs = await connection.fetch(
            "SELECT hypertable_name, config->>'drop_after' AS nach FROM timescaledb_information.jobs "
            "WHERE proc_name = 'policy_retention' ORDER BY 1")
        assert [(j["hypertable_name"], j["nach"]) for j in jobs] == [("messwert", "365 days")]
        await connection.execute(
            "UPDATE skytech_config.einstellung SET wert = '10' WHERE schluessel = 'aufbewahrung_minutenwerte_tage'")
        with pytest.raises(asyncpg.RaiseError, match="mindestens 31"):
            await connection.execute("SELECT skytech_config.aufbewahrung_anwenden()")
        await connection.execute(
            "UPDATE skytech_config.einstellung SET wert = 'null' WHERE schluessel = 'aufbewahrung_minutenwerte_tage'")


async def test_role_privileges(clean):
    app_pool, collector_pool = clean
    async with app_pool.acquire() as connection:
        await _sensor(connection)
    reader = await _pool("skytech_reader")
    try:
        async with reader.acquire() as connection:
            assert await connection.fetchval("SELECT count(*) FROM skytech.v_messwert_1min") == 0
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await connection.execute("DELETE FROM skytech.sensor")
    finally:
        await reader.close()
    async with collector_pool.acquire() as connection:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute("DELETE FROM skytech.sensor")


async def test_sensor_service_errors_and_protocol(clean):
    app_pool, _ = clean
    async with app_pool.acquire() as connection:
        sensor_id = await _sensor(connection, rolle="ist", soll_ist_paar="Heizstab")
        with pytest.raises(sensor_service.ValidationError) as duplicate:
            await _sensor(connection)
        assert "0.entity_id" in duplicate.value.field_errors
        with pytest.raises(sensor_service.ValidationError) as pair:
            await _sensor(connection, "sensor.anderer", rolle="ist", soll_ist_paar="Heizstab")
        assert "0.soll_ist_paar" in pair.value.field_errors
        with pytest.raises(sensor_service.ValidationError) as unknown:
            await _sensor(connection, "sensor.dritter", kategorie="gibtsnicht")
        assert "0.kategorie" in unknown.value.field_errors

        await sensor_service.update_sensor(connection, sensor_id, {"aktiv": False}, "nico")
        await sensor_service.delete_sensor(connection, sensor_id, "nico")
        actions = await connection.fetch(
            "SELECT aktion, benutzer FROM skytech_config.aenderungsprotokoll ORDER BY id DESC LIMIT 2")
        assert [(a["aktion"], a["benutzer"]) for a in actions] == [("sensor_geloescht", "nico"), ("sensor_geaendert", "nico")]


async def _wait_for(predicate, timeout=5.0):
    for _ in range(int(timeout / 0.05)):
        if await predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("Bedingung nicht erfüllt")


async def test_collector_end_to_end(clean, unused_tcp_port):
    app_pool, collector_pool = clean
    now = datetime.now(timezone.utc).replace(microsecond=0)
    old = now - timedelta(hours=2)
    async with app_pool.acquire() as connection:
        power = await _sensor(connection, "sensor.pv_leistung")
        # Letzter gespeicherter Wert liegt zwei Stunden zurück: Lücke nachladen.
        await connection.execute("INSERT INTO skytech.messwert VALUES ($1, $2, 100, NULL)", old, power)

    ha = FakeHomeAssistant(
        states=[
            {"entity_id": "sensor.pv_leistung", "state": "300", "attributes": {"unit_of_measurement": "W"},
             "last_changed": (now - timedelta(minutes=5)).isoformat(), "last_updated": (now - timedelta(minutes=5)).isoformat()},
            {"entity_id": "climate.wp", "state": "heat", "attributes": {"current_temperature": 21.5},
             "last_changed": old.isoformat(), "last_updated": (now - timedelta(minutes=1)).isoformat()},
        ],
        history={"sensor.pv_leistung": [
            {"s": "100", "a": {}, "lu": old.timestamp()},
            {"s": "200", "a": {}, "lu": (now - timedelta(hours=1)).timestamp()},
            {"s": "300", "a": {}, "lu": (now - timedelta(minutes=5)).timestamp()},
        ]},
    )
    await ha.start(unused_tcp_port)
    collector = Collector(app_pool, collector_pool)
    await collector.start()
    client = HAClient(ha.url, "geheim", collector.on_state_changed, collector.on_connected)
    collector.ha = client
    task = asyncio.create_task(client.run())

    async def values(sensor_id):
        async with app_pool.acquire() as connection:
            return [r["wert"] for r in await connection.fetch(
                "SELECT wert FROM skytech.messwert WHERE sensor_id = $1 ORDER BY zeit", sensor_id)]

    try:
        await asyncio.wait_for(ha.subscribed.wait(), 5)
        await _wait_for(lambda: _equals(values(power), [100.0, 200.0, 300.0]))

        # Live-Wert
        await ha.send_state({"entity_id": "sensor.pv_leistung", "state": "400", "attributes": {},
                             "last_changed": now.isoformat(), "last_updated": now.isoformat()})
        await _wait_for(lambda: _equals(values(power), [100.0, 200.0, 300.0, 400.0]))

        # Neuer Attribut-Sensor über SQL: NOTIFY, sofort mit aktuellem Wert.
        async with app_pool.acquire() as connection:
            temperature = await _sensor(connection, "climate.wp", attribut="current_temperature", groesse="temperatur")
        await _wait_for(lambda: _equals(values(temperature), [21.5]))

        await collector.compute_minutes(now + timedelta(minutes=1))
        async with app_pool.acquire() as connection:
            minutes = await connection.fetchval(
                "SELECT count(*) FROM skytech.messwert_1min WHERE sensor_id = $1", power)
        # Nachgeladene zwei Stunden plus laufende Minuten.
        assert minutes >= 120
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await collector.stop()
        await ha.stop()


async def _equals(awaitable, expected):
    return await awaitable == expected
