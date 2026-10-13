"""Integrationstests gegen eine echte TimescaleDB.

Laufen nur, wenn SKYTECH_TEST_DSN auf einen Superuser zeigt, z. B.
`postgresql://postgres:test@127.0.0.1:15432/postgres` (docs/test-strategie.md).
Jeder Lauf legt die Datenbank `skytech_test` neu an. Rollen werden per
`server_settings.role` gesetzt, damit die Rechte der echten Rollen gelten.
"""

import asyncio
import json
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
ROLES = ("skytech_app", "skytech_collector", "skytech_admin", "skytech_reader", "skytech_hems")
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
        assert [m.version for m in applied] == [1, 2, 3, 4, 5]
        assert await connection.fetchval("SELECT bezeichnung FROM skytech.groesse WHERE schluessel = 'preis'") == "Preis"
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


# ---------------------------------------------------------------------------
# MCP-Werkzeuge (Sicherung durch Attrappe ersetzt – pg_dump braucht den Container)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(loop_scope="module")
async def mcp_tools(clean, tmp_path, monkeypatch):
    import backup
    from mcp_tools import McpTools

    made = []

    async def fake_create(prefix, directory=None):
        made.append(prefix)
        return backup.BackupFile(f"{prefix}_test.dump", 1, datetime.now(timezone.utc))

    monkeypatch.setattr(backup, "create", fake_create)
    admin = await _pool("skytech_admin")
    tools = McpTools(admin, grafana=None, site_dir=tmp_path / "migrations", backup_dir=tmp_path)
    yield tools, made, clean[0]
    await admin.close()


async def test_mcp_query_is_read_only(mcp_tools):
    from mcp_tools import ToolError
    tools, made, _ = mcp_tools
    result = await tools.query("SELECT schluessel FROM skytech.kategorie ORDER BY reihenfolge", max_rows=2)
    assert result["zeilen"] == [["pv"], ["speicher"]] and result["abgeschnitten"] is True
    with pytest.raises(ToolError, match="read-only"):
        await tools.query("DELETE FROM skytech.kategorie")
    assert made == []


async def test_mcp_execute_backs_up_and_logs(mcp_tools):
    tools, made, app_pool = mcp_tools
    result = await tools.execute("INSERT INTO skytech.kategorie VALUES ('wallbox', 'Wallbox', 35)", "Wallbox ergänzen")
    assert result["ergebnis"] == "INSERT 0 1" and made == ["mcp"]
    async with app_pool.acquire() as connection:
        entry = await connection.fetchrow(
            "SELECT quelle, aktion, details->>'begruendung' AS grund FROM skytech_config.aenderungsprotokoll ORDER BY id DESC LIMIT 1")
        await connection.execute("DELETE FROM skytech.kategorie WHERE schluessel = 'wallbox'")
    assert (entry["quelle"], entry["aktion"], entry["grund"]) == ("mcp", "sql_ausgefuehrt", "Wallbox ergänzen")


async def test_mcp_migration_success_and_rollback(mcp_tools):
    from mcp_tools import ToolError
    tools, _, app_pool = mcp_tools
    result = await tools.create_migration("wallbox_ladevorgang",
                                          "CREATE TABLE skytech.ladevorgang (beginn timestamptz PRIMARY KEY, kwh double precision);",
                                          "Ladevorgänge der Wallbox")
    assert result["datei"].startswith("1") and result["datei"].endswith("_wallbox_ladevorgang.sql")
    async with app_pool.acquire() as connection:
        owner = await connection.fetchval("SELECT tableowner FROM pg_tables WHERE tablename = 'ladevorgang'")
    assert owner == "skytech_app"

    with pytest.raises(ToolError, match="entfernt"):
        await tools.create_migration("kaputt", "CREATE TABLE skytech.x (;", "Test")
    names = [path.name for path in (tools._site_dir).iterdir()]
    assert not any("kaputt" in name for name in names)


async def test_mcp_schema_and_retention(mcp_tools):
    tools, _, _ = mcp_tools
    schema = await tools.schema("skytech")
    kinds = {item["name"]: item["art"] for item in schema["objekte"]}
    assert kinds["messwert_15min"] == "continuous_aggregate"
    assert kinds["v_soll_ist"] == "view" and kinds["sensor"] == "tabelle"
    result = await tools.set_retention(400, None)
    assert result["rohwerte_tage"] == 400
    await tools.set_retention(365, None)


# ---------------------------------------------------------------------------
# Speicher und Aufbewahrung (M3)
# ---------------------------------------------------------------------------

async def test_storage_and_retention(clean):
    import settings_service
    app_pool, _ = clean
    async with app_pool.acquire() as connection:
        sensor_id = await _sensor(connection)
        await connection.execute("INSERT INTO skytech.messwert (zeit, sensor_id, wert) VALUES (now(), $1, 1)", sensor_id)
        info = await settings_service.storage(connection)
        names = {row["name"] for row in info["tabellen"]}
        assert {"messwert", "messwert_1min", "messwert_15min", "messwert_1h", "messwert_1d"} <= names
        assert info["datenbank_bytes"] > 0 and info["rohwerte_je_tag"][-1]["rohwerte"] == 1
        assert len(info["rohwerte_je_tag"][-1]["tag"]) == 10

        await settings_service.set_retention(connection, 400, 60)
        assert await settings_service.read_retention(connection) == {"rohwerte_tage": 400, "minutenwerte_tage": 60}
        jobs = await connection.fetchval(
            "SELECT count(*) FROM timescaledb_information.jobs WHERE proc_name = 'policy_retention'")
        assert jobs == 2
        await settings_service.set_retention(connection, 365, None)
        assert await settings_service.read_retention(connection) == {"rohwerte_tage": 365, "minutenwerte_tage": None}


async def test_change_log_paging_and_filter(clean):
    app_pool, _ = clean
    async with app_pool.acquire() as connection:
        await connection.execute("TRUNCATE skytech_config.aenderungsprotokoll")
        for number in range(5):
            await sensor_service.log_change(connection, "nico", "test", {"nr": number},
                                            source="mcp" if number % 2 else "ui")
        first, more = await sensor_service.list_changes(connection, limit=2)
        assert [entry["details"]["nr"] for entry in first] == [4, 3] and more
        rest, more = await sensor_service.list_changes(connection, before_id=first[-1]["id"], limit=10)
        assert [entry["details"]["nr"] for entry in rest] == [2, 1, 0] and not more
        mcp, _ = await sensor_service.list_changes(connection, source="mcp")
        assert {entry["quelle"] for entry in mcp} == {"mcp"} and len(mcp) == 2


async def test_migration_overview_states(pools, tmp_path):
    app_pool, _ = pools
    site = tmp_path / "anlage"
    site.mkdir()
    (site / "1900_offen.sql").write_text("SELECT 1;", encoding="utf-8")
    async with app_pool.acquire() as connection:
        items = await migration_runner.overview(connection, migration_runner.discover(site_dir=site))
        states = {item["version"]: item["status"] for item in items}
        assert states[1] == states[2] == "angewendet" and states[1900] == "ausstehend"

        changed = tmp_path / "sql"
        changed.mkdir()
        original = (migration_runner.SYSTEM_DIR / "0001_grundschema.sql").read_text(encoding="utf-8")
        (changed / "0001_grundschema.sql").write_text(original + "\n-- geändert\n", encoding="utf-8")
        items = await migration_runner.overview(connection, migration_runner.discover(changed, tmp_path / "leer"))
        states = {item["version"]: item["status"] for item in items}
        assert states[1] == "geaendert" and states[2] == "datei_fehlt"


# ---------------------------------------------------------------------------
# SkytechHEMS (D-027, Vertrag contract_hems_data_insight 0.3)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(loop_scope="module")
async def hems(clean):
    async with clean[0].acquire() as connection:
        await connection.execute("TRUNCATE skytech.prognose_lauf RESTART IDENTITY CASCADE")
    pool = await _pool("skytech_hems")
    yield pool
    await pool.close()


async def _sichern(connection, entity_id, quelle="ha", name=None, kategorie="verbraucher", groesse="leistung",
                   einheit="W", attribut=None, zaehler=False):
    return await connection.fetchval(
        "SELECT skytech.hems_sensor_sichern($1, $2, $3, $4, $5, $6, $7, $8)",
        entity_id, attribut, name or entity_id, kategorie, groesse, einheit, quelle, zaehler)


async def test_hems_role_only_reads_and_calls_functions(clean, hems):
    async with hems.acquire() as connection:
        assert await connection.fetchval("SELECT version FROM skytech.v_hems_vertrag") == "0.3"
        assert await connection.fetchval("SELECT count(*) FROM skytech.v_hems_rolle_1min") == 0
        assert await connection.fetchval("SELECT count(*) FROM skytech.v_messwert_15min") == 0
        for statement in (
            "INSERT INTO skytech.sensor (entity_id, name, kategorie, groesse) VALUES ('sensor.x', 'x', 'pv', 'leistung')",
            "INSERT INTO skytech.messwert VALUES (now(), 1, 1, NULL)",
            "INSERT INTO skytech.prognose_lauf (art, quelle, erstellt, raster_min, gueltig_ab, gueltig_bis, einheit) "
            "VALUES ('preis', 'x', now(), 15, now(), now() + interval '1 hour', '€/kWh')",
            "SELECT * FROM skytech_config.aenderungsprotokoll",
            "SELECT skytech_config.hems_protokoll('x', '{}')",
        ):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await connection.execute(statement)
    async with clean[0].acquire() as connection:
        # Die Schreibfunktionen sind nicht für alle freigegeben.
        reader = await _pool("skytech_reader")
        try:
            async with reader.acquire() as reader_connection:
                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    await _sichern(reader_connection, "sensor.x")
        finally:
            await reader.close()


async def test_hems_adopts_existing_sensor_and_locks_it(clean, hems):
    app_pool, _ = clean
    async with app_pool.acquire() as connection:
        existing = await _sensor(connection, "sensor.e3dc_leistung_haus_modbus", anlage="Haus")
    async with hems.acquire() as connection:
        adopted = await _sichern(connection, "sensor.e3dc_leistung_haus_modbus", name="Hausverbrauch")
        created = await _sichern(connection, "sensor.pv_ist", kategorie="pv")
        own = await _sichern(connection, "hems.grundlast_w", quelle="hems")
        assert adopted == existing and created != existing
        # Erneut sichern ändert nichts und liefert dieselbe ID.
        assert await _sichern(connection, "sensor.e3dc_leistung_haus_modbus", name="Hausverbrauch") == existing
        with pytest.raises(asyncpg.PostgresError, match="passt nicht zur Quelle"):
            await _sichern(connection, "hems.falsch", quelle="ha")
        await connection.execute("SELECT skytech.hems_zuordnen('hausverbrauch', $1)", existing)
    async with app_pool.acquire() as connection:
        # Von Hand angelegt, aber mit hems.-Namen: das HEMS übernimmt keinen Sensor mit falscher Quelle.
        foreign = await _sensor(connection, "hems.fremd")
    async with hems.acquire() as connection:
        with pytest.raises(asyncpg.PostgresError, match="hat die Quelle"):
            await _sichern(connection, "hems.fremd", quelle="hems")

    async with app_pool.acquire() as connection:
        rows = {row["id"]: row for row in await sensor_service.list_sensors(connection)}
        assert rows[existing]["verwaltet_von"] == "hems" and rows[existing]["name"] == "Hausverbrauch"
        assert rows[existing]["anlage"] == "Haus"  # nicht vom HEMS gesetzte Felder bleiben
        assert rows[existing]["hems_rollen"] == ["hausverbrauch"] and rows[created]["hems_rollen"] == []
        assert rows[own]["quelle"] == "hems" and rows[foreign]["verwaltet_von"] is None
        with pytest.raises(sensor_service.LockedError):
            await sensor_service.update_sensor(connection, existing, {"aktiv": False}, "nico")
        with pytest.raises(sensor_service.LockedError):
            await sensor_service.delete_sensor(connection, existing, "nico")
        # Auch direktes SQL scheitert am Trigger.
        with pytest.raises(asyncpg.PostgresError) as locked:
            await connection.execute("UPDATE skytech.sensor SET name = 'x' WHERE id = $1", existing)
        assert locked.value.sqlstate == "SKY01"
        actions = [row["aktion"] for row in await connection.fetch(
            "SELECT aktion FROM skytech_config.aenderungsprotokoll WHERE quelle = 'hems' ORDER BY id")]
        assert actions == ["hems_sensor_uebernommen", "hems_sensor_aktualisiert", "hems_sensor_angelegt",
                           "hems_sensor_angelegt", "hems_zuordnung"]


async def test_hems_swaps_sensor_behind_role_without_gap(clean, hems):
    app_pool, collector_pool = clean
    async with hems.acquire() as connection:
        old = await _sichern(connection, "sensor.haus_alt")
        await connection.execute("SELECT skytech.hems_zuordnen('hausverbrauch', $1)", old)
        await asyncio.sleep(0.01)
        new = await _sichern(connection, "sensor.haus_neu")
        await connection.execute("SELECT skytech.hems_zuordnen('hausverbrauch', $1)", new)
        await connection.execute("SELECT skytech.hems_zuordnen('hausverbrauch', $1)", new)  # unverändert: nichts
        await connection.execute("SELECT skytech.hems_sensor_stilllegen($1)", old)
        mapping = await connection.fetch(
            "SELECT sensor_id, isfinite(gueltig_ab) AS endlich, gueltig_ab, gueltig_bis FROM skytech.v_hems_zuordnung "
            "WHERE rolle = 'hausverbrauch' ORDER BY gueltig_ab")
    assert [row["sensor_id"] for row in mapping] == [old, new]
    # Die erste Zuordnung gilt ab -infinity: auch die Historie eines übernommenen Sensors zählt.
    assert mapping[0]["endlich"] is False and mapping[1]["endlich"] is True
    switch = mapping[1]["gueltig_ab"]
    assert mapping[0]["gueltig_bis"] == switch and mapping[1]["gueltig_bis"] is None

    start = minute_values.floor_minute(switch) - timedelta(minutes=45)
    async with app_pool.acquire() as connection:
        assert await connection.fetchval("SELECT aktiv FROM skytech.sensor WHERE id = $1", old) is False
        await connection.execute("INSERT INTO skytech.messwert VALUES ($1, $2, 100, NULL), ($1, $3, 200, NULL)",
                                 start, old, new)
    async with collector_pool.acquire() as connection:
        await minute_values.compute(connection, start, start + timedelta(minutes=90), [old, new])
    async with hems.acquire() as connection:
        rows = await connection.fetch(
            "SELECT zeit, sensor_id FROM skytech.v_hems_rolle_15min WHERE rolle = 'hausverbrauch' ORDER BY zeit")
    assert rows and len({row["zeit"] for row in rows}) == len(rows)
    assert all(row["sensor_id"] == (old if row["zeit"] < switch else new) for row in rows)
    assert {row["sensor_id"] for row in rows} == {old, new}


async def test_hems_series_written_late_are_recomputed(clean, hems):
    app_pool, collector_pool = clean
    async with hems.acquire() as connection:
        series = await _sichern(connection, "hems.grundlast_w", quelle="hems")
        ha_sensor = await _sichern(connection, "sensor.haus")
    collector = Collector(app_pool, collector_pool)
    await collector.start()
    try:
        assert series in collector.active_sensor_ids and series not in collector.ha_sensor_ids
        assert ha_sensor in collector.ha_sensor_ids
        slot = minute_values.floor_minute(datetime.now(timezone.utc)) - timedelta(minutes=30)
        slot = slot.replace(minute=slot.minute - slot.minute % 15)
        async with hems.acquire() as connection:
            written = await connection.fetchval(
                "SELECT skytech.hems_messwerte_schreiben($1, $2, $3)", series, [slot, slot + timedelta(minutes=15)],
                [1100.0, 900.0])
            assert written == 2
            assert await connection.fetchval(
                "SELECT skytech.hems_messwerte_schreiben($1, $2, $3)", series, [slot], [5.0]) == 0
            for zeiten, werte, text in (
                ([datetime.now(timezone.utc) + timedelta(hours=1)], [1.0], "Zukunft"),
                ([slot], [float("nan")], "endlich"),
                ([slot, slot], [1.0], "gleich lang"),
            ):
                with pytest.raises(asyncpg.PostgresError, match=text):
                    await connection.execute("SELECT skytech.hems_messwerte_schreiben($1, $2, $3)", series, zeiten, werte)
            with pytest.raises(asyncpg.PostgresError, match="Quelle hems"):
                await connection.execute("SELECT skytech.hems_messwerte_schreiben($1, $2, $3)", ha_sensor, [slot], [1.0])
        await _wait_for(lambda: _is_late(collector, series))
        await collector.compute_minutes(datetime.now(timezone.utc))
        async with app_pool.acquire() as connection:
            first = await connection.fetchval(
                "SELECT mittel FROM skytech.messwert_15min WHERE sensor_id = $1 AND zeit = $2", series, slot)
        assert first == pytest.approx(1100.0)
    finally:
        await collector.stop()


async def _is_late(collector, sensor_id):
    return sensor_id in collector._late


async def _lauf(connection, art, erstellt, ab, werte, raster=15, details=None, p10=None, p90=None):
    zeiten = [ab + timedelta(minutes=raster * i) for i in range(len(werte))]
    return await connection.fetchval(
        "SELECT skytech.hems_lauf_schreiben($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)",
        art, "test", erstellt, raster, ab, ab + timedelta(minutes=raster * max(len(werte), 1)),
        "€/kWh" if art == "preis" else "W", None, json.dumps(details if details is not None else {}),
        zeiten, werte, p10, p90)


async def test_hems_runs_views_and_cleanup(clean, hems):
    app_pool, collector_pool = clean
    day = datetime(2026, 10, 10, 22, 0, tzinfo=timezone.utc)  # 11.10.2026 00:00 in Berlin
    pv_details = {"entity": "sensor.helios", "ist_rolle": "pv_ist", "heute_kwh": 1, "morgen_kwh": 2, "rest_heute_kwh": 0}
    async with hems.acquire() as connection:
        # Vortagslauf und ein jüngerer Lauf für dieselben Slots.
        await _lauf(connection, "pv", day - timedelta(days=1), day, [1000.0, 2000.0], details=pv_details,
                    p10=[800.0, 1500.0], p90=[1200.0, 2500.0])
        await _lauf(connection, "pv", day - timedelta(hours=1), day, [1100.0, 2100.0], details=pv_details)
        await _lauf(connection, "preis", day - timedelta(hours=10), day, [0.30, 0.20], raster=60,
                    details={"entity": "sensor.epex"})
        await _lauf(connection, "auswertung", day, day, [], details={"reichweite_h": 5})
        for args, text in (
            (("pv", day, day, [1.0], 15, {"entity": "x"}), "fehlt: ist_rolle"),
            (("pv", day, day, [1.0], 60, pv_details), "15-min-Raster"),
            (("auswertung", day, day, [1.0], 15, {}), "keine Werte"),
            (("gibtsnicht", day, day, [1.0], 15, {}), "Unbekannte Art"),
        ):
            with pytest.raises(asyncpg.PostgresError, match=text):
                await _lauf(connection, *args[:4], raster=args[4], details=args[5])

        pv_ist = await _sichern(connection, "sensor.pv_ist", kategorie="pv")
        await connection.execute("SELECT skytech.hems_zuordnen('pv_ist', $1)", pv_ist)
    async with app_pool.acquire() as connection:
        await connection.execute("INSERT INTO skytech.messwert VALUES ($1, $2, 900, NULL)", day, pv_ist)
    async with collector_pool.acquire() as connection:
        await minute_values.compute(connection, day, day + timedelta(minutes=30), [pv_ist])

    async with hems.acquire() as connection:
        current = await connection.fetch("SELECT wert FROM skytech.v_prognose_aktuell WHERE art = 'pv' ORDER BY zeit")
        assert [row["wert"] for row in current] == [1100.0, 2100.0]
        prices = await connection.fetch("SELECT zeit, bis, preis_eur_kwh FROM skytech.v_preis ORDER BY zeit")
        assert [row["preis_eur_kwh"] for row in prices] == [0.30, 0.20]
        assert prices[0]["bis"] - prices[0]["zeit"] == timedelta(hours=1)
        compared = await connection.fetch(
            "SELECT prognose, prognose_vortag, ist FROM skytech.v_prognose_vs_ist WHERE art = 'pv' ORDER BY zeit")
        assert (compared[0]["prognose"], compared[0]["prognose_vortag"], compared[0]["ist"]) == (1100.0, 1000.0, 900.0)
        quality = await connection.fetchrow("SELECT * FROM skytech.v_prognose_guete_tag WHERE art = 'pv'")
        assert quality["slots"] == 2 and quality["anteil_im_band"] == pytest.approx(0.5)
        assert quality["tag"].astimezone(timezone(timedelta(hours=2))).hour == 0

    async with app_pool.acquire() as connection:
        await connection.execute(
            "UPDATE skytech_config.einstellung SET wert = '1' WHERE schluessel = 'aufbewahrung_prognose_tage'")
        try:
            await connection.execute("CALL skytech_config.prognose_aufraeumen(0, '{}')")
        finally:
            await connection.execute(
                "UPDATE skytech_config.einstellung SET wert = '365' WHERE schluessel = 'aufbewahrung_prognose_tage'")
        remaining = [row["art"] for row in await connection.fetch("SELECT art FROM skytech.prognose_lauf ORDER BY id")]
        assert remaining == ["preis"]
        assert await connection.fetchval("SELECT count(*) FROM skytech.prognose_wert") == 2


async def test_hems_series_are_not_carried_forward(clean, hems):
    app_pool, collector_pool = clean
    async with hems.acquire() as connection:
        series = await _sichern(connection, "hems.grundlast_w", quelle="hems")
        await connection.execute("SELECT skytech.hems_zuordnen('grundlast', $1)", series)
        ha_sensor = await _sichern(connection, "sensor.haus")
    start = minute_values.floor_minute(datetime.now(timezone.utc)) - timedelta(minutes=30)
    async with hems.acquire() as connection:
        await connection.execute("SELECT skytech.hems_messwerte_schreiben($1, $2, $3)", series,
                                 [start, start + timedelta(minutes=3)], [400.0, 700.0])
    async with app_pool.acquire() as connection:
        await connection.execute("INSERT INTO skytech.messwert VALUES ($1, $2, 500, NULL)", start, ha_sensor)
    async with collector_pool.acquire() as connection:
        await minute_values.compute(connection, start, start + timedelta(minutes=6), [series, ha_sensor])
    async with hems.acquire() as connection:
        rows = await connection.fetch(
            "SELECT zeit, mittel, anzahl, abdeckung_s FROM skytech.v_hems_rolle_1min WHERE rolle = 'grundlast' "
            "ORDER BY zeit")
    # Nur die beiden Minuten mit Rohwert, jeweils voll abgedeckt – keine Fortführung dazwischen.
    assert [(row["zeit"], row["mittel"], row["anzahl"], row["abdeckung_s"]) for row in rows] == [
        (start, 400.0, 1, 60.0), (start + timedelta(minutes=3), 700.0, 1, 60.0)]
    async with app_pool.acquire() as connection:
        # Home-Assistant-Sensoren führen ihren letzten Wert weiter fort.
        assert await connection.fetchval(
            "SELECT count(*) FROM skytech.messwert_1min WHERE sensor_id = $1", ha_sensor) == 6


async def test_hems_counter_roles_and_cleanup_of_carried_minutes(clean, hems):
    app_pool, collector_pool = clean
    async with hems.acquire() as connection:
        counter = await _sichern(connection, "sensor.netz_bezug_energie", kategorie="netz", groesse="energie",
                                 einheit="kWh", zaehler=True)
        await connection.execute("SELECT skytech.hems_zuordnen('netz_bezug_energie', $1)", counter)
        with pytest.raises(asyncpg.PostgresError, match="keine Zähler"):
            await _sichern(connection, "hems.zaehler", quelle="hems", zaehler=True)
    start = minute_values.floor_minute(datetime.now(timezone.utc)) - timedelta(minutes=10)
    async with app_pool.acquire() as connection:
        assert await connection.fetchval("SELECT energie_zaehler FROM skytech.sensor WHERE id = $1", counter)
        await connection.execute(
            "INSERT INTO skytech.messwert VALUES ($1, $3, 100.0, NULL), ($2, $3, 100.5, NULL)",
            start, start + timedelta(minutes=1, seconds=30), counter)
    async with collector_pool.acquire() as connection:
        await minute_values.compute(connection, start, start + timedelta(minutes=3), [counter])
    async with hems.acquire() as connection:
        growth = await connection.fetch(
            "SELECT zeit, zuwachs FROM skytech.v_hems_rolle_1min WHERE rolle = 'netz_bezug_energie' ORDER BY zeit")
    assert [row["zuwachs"] for row in growth] == [0.0, 0.5, 0.0]
    # Später zum Nicht-Zähler gemacht: das Kennzeichen folgt der Funktion.
    async with hems.acquire() as connection:
        await _sichern(connection, "sensor.netz_bezug_energie", kategorie="netz", groesse="energie", einheit="kWh")
    async with app_pool.acquire() as connection:
        assert await connection.fetchval("SELECT energie_zaehler FROM skytech.sensor WHERE id = $1", counter) is False

    # Bereinigung aus 0004: fortgeführte Minuten (anzahl = 0) einer HEMS-Reihe entfallen, echte bleiben.
    # Wie an der Referenzanlage liegt ein älterer, komprimierter Chunk mit Werten anderer Sensoren
    # daneben; die Bereinigung darf ihn nicht entpacken (Grenze hier 1 statt 100 000).
    async with hems.acquire() as connection:
        series = await _sichern(connection, "hems.nutzbar_kwh", quelle="hems", kategorie="speicher",
                                groesse="energie", einheit="kWh")
        await connection.execute("SELECT skytech.hems_messwerte_schreiben($1, $2, $3)", series, [start], [5.0])
    old = start - timedelta(days=45)
    async with app_pool.acquire() as connection:
        other = await _sensor(connection, "sensor.alt")
        await connection.executemany(
            "INSERT INTO skytech.messwert_1min (zeit, sensor_id, mittel, minimum, maximum, letzter, anzahl, abdeckung_s) "
            "VALUES ($1, $2, 1, 1, 1, 1, 0, 60)", [(old + timedelta(minutes=i), other) for i in range(50)])
        await connection.execute(
            "SELECT compress_chunk(c) FROM show_chunks('skytech.messwert_1min', older_than => $1::timestamptz) c",
            start - timedelta(days=1))
        assert await connection.fetchval(
            "SELECT count(*) FROM timescaledb_information.chunks WHERE hypertable_name = 'messwert_1min' "
            "AND is_compressed AND range_end <= $1", start) >= 1
        await connection.execute(
            "INSERT INTO skytech.messwert_1min (zeit, sensor_id, mittel, minimum, maximum, letzter, anzahl, abdeckung_s) "
            "VALUES ($1, $3, 5, 5, 5, 5, 1, 60), ($2, $3, 5, 5, 5, 5, 0, 60) ON CONFLICT DO NOTHING",
            start, start + timedelta(minutes=1), series)
        sql = (migration_runner.SYSTEM_DIR / "0004_hems_minuten.sql").read_text(encoding="utf-8")
        cleanup = sql[sql.index("-- Bereinigung: Anfang"):sql.index("-- Bereinigung: Ende")]
        # Das alte DELETE mit Join scheitert an der Grenze – so wie am 13.10.2026 an der Anlage.
        async with connection.transaction():
            await connection.execute("SET LOCAL timescaledb.max_tuples_decompressed_per_dml_transaction = 1")
            with pytest.raises(asyncpg.PostgresError, match="decompression limit"):
                async with connection.transaction():
                    await connection.execute(
                        "DELETE FROM skytech.messwert_1min m USING skytech.sensor s "
                        "WHERE s.id = m.sensor_id AND s.quelle = 'hems' AND m.anzahl = 0")
        async with connection.transaction():
            await connection.execute("SET LOCAL timescaledb.max_tuples_decompressed_per_dml_transaction = 1")
            await connection.execute(cleanup)
        assert await connection.fetchval(
            "SELECT array_agg(anzahl ORDER BY zeit) FROM skytech.messwert_1min WHERE sensor_id = $1", series) == [1]
        assert await connection.fetchval(
            "SELECT count(*) FROM skytech.messwert_1min WHERE sensor_id = $1", other) == 50


# ---------------------------------------------------------------------------
# Robustheit bei Neustarts (13.10.2026)
# ---------------------------------------------------------------------------

async def test_backfill_in_small_windows_retries_and_keeps_older_values(clean, unused_tcp_port, monkeypatch):
    import collector as collector_module

    monkeypatch.setattr(collector_module, "BACKFILL_RETRY_S", (0.05,))
    app_pool, collector_pool = clean
    now = datetime.now(timezone.utc).replace(microsecond=0)
    old = now - timedelta(hours=3)
    async with app_pool.acquire() as connection:
        power = await _sensor(connection, "sensor.pv_leistung")
        quiet = await _sensor(connection, "sensor.heizluefter", kategorie="verbraucher")
        await connection.execute("INSERT INTO skytech.messwert VALUES ($1, $2, 100, NULL)", old, power)
        # Seit Tagen unverändert: darf den Beginn der Lücke nicht nach vorn ziehen (0.7.1).
        await connection.execute("INSERT INTO skytech.messwert VALUES ($1, $2, 0, NULL)",
                                 now - timedelta(days=3), quiet)
    history = [{"s": str(100 + i), "a": {}, "lu": (old + timedelta(minutes=10 * i)).timestamp()} for i in range(1, 18)]
    ha = FakeHomeAssistant(
        states=[{"entity_id": "sensor.pv_leistung", "state": "999", "attributes": {},
                 "last_changed": now.isoformat(), "last_updated": now.isoformat()}],
        history={"sensor.pv_leistung": history})
    ha.fail_history = 1                                    # erster Versuch: HA trennt die Verbindung
    await ha.start(unused_tcp_port)
    collector = Collector(app_pool, collector_pool)
    await collector.start()
    client = HAClient(ha.url, "geheim", collector.on_state_changed, collector.on_connected)
    collector.ha = client
    task = asyncio.create_task(client.run())

    async def done():
        async with app_pool.acquire() as connection:
            return await connection.fetchval(
                "SELECT count(*) FROM skytech_config.nachlade_luecke WHERE erledigt_am IS NULL") == 0 and \
                await connection.fetchval("SELECT count(*) FROM skytech.messwert WHERE sensor_id = $1", power) == 19

    try:
        await _wait_for(done, timeout=15)
        async with app_pool.acquire() as connection:
            values = [row["wert"] for row in await connection.fetch(
                "SELECT wert FROM skytech.messwert WHERE sensor_id = $1 ORDER BY zeit", power)]
            gaps = await connection.fetch("SELECT von, bis, erledigt_am FROM skytech_config.nachlade_luecke")
        # Alte Werte landen trotz des schon aufgenommenen aktuellen Zustands (999).
        assert values == [100.0] + [100.0 + i for i in range(1, 18)] + [999.0]
        # Lücke beginnt beim jüngsten Rohwert aller Sensoren, nicht beim ältesten.
        assert min(gap["von"] for gap in gaps) >= old
        windows = [c for c in ha.commands if c["type"] == "history/history_during_period"]
        assert all(datetime.fromisoformat(c["end_time"]) - datetime.fromisoformat(c["start_time"])
                   <= timedelta(hours=1) for c in windows)
        assert all(c["no_attributes"] for c in windows) and all(len(c["entity_ids"]) <= 5 for c in windows)
        assert collector.backfill_status is None
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await collector.stop()
        await ha.stop()


async def test_open_gap_survives_restart(clean, unused_tcp_port):
    app_pool, collector_pool = clean
    now = datetime.now(timezone.utc).replace(microsecond=0)
    async with app_pool.acquire() as connection:
        power = await _sensor(connection, "sensor.pv_leistung")
        await connection.execute("INSERT INTO skytech.messwert VALUES ($1, $2, 1, NULL)", now - timedelta(seconds=2),
                                 power)
        # Von einem früheren Lauf offen geblieben, zur Hälfte geladen.
        await connection.execute(
            "INSERT INTO skytech_config.nachlade_luecke (von, bis, versuche, letzter_fehler) VALUES ($1, $2, 2, 'x')",
            now - timedelta(hours=2), now - timedelta(hours=1))
    ha = FakeHomeAssistant(history={"sensor.pv_leistung": [
        {"s": "50", "a": {}, "lu": (now - timedelta(minutes=90)).timestamp()}]})
    await ha.start(unused_tcp_port)
    collector = Collector(app_pool, collector_pool)
    await collector.start()
    client = HAClient(ha.url, "geheim", collector.on_state_changed, collector.on_connected)
    collector.ha = client
    task = asyncio.create_task(client.run())

    async def loaded():
        async with app_pool.acquire() as connection:
            return await connection.fetchval(
                "SELECT count(*) FROM skytech.messwert WHERE sensor_id = $1 AND wert = 50", power) == 1

    try:
        await _wait_for(loaded, timeout=10)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await collector.stop()
        await ha.stop()


async def test_hems_values_without_notify_get_minutes_on_start(clean, hems):
    app_pool, collector_pool = clean
    async with hems.acquire() as connection:
        series = await _sichern(connection, "hems.grundlast_w", quelle="hems")
    minute = minute_values.floor_minute(datetime.now(timezone.utc)) - timedelta(minutes=20)
    collector = Collector(app_pool, collector_pool)
    await collector.start()
    try:
        # Geschrieben, während niemand zuhört (wie im Neustart-Fenster): direkt, ohne NOTIFY.
        async with app_pool.acquire() as connection:
            await connection.execute("INSERT INTO skytech.messwert VALUES ($1, $2, 750, NULL)", minute, series)
        await collector.recheck_hems_series(datetime.now(timezone.utc))
        await collector.compute_minutes(datetime.now(timezone.utc))
        async with app_pool.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT mittel, anzahl FROM skytech.messwert_1min WHERE sensor_id = $1 AND zeit = $2", series, minute)
        assert row is not None and row["mittel"] == 750.0 and row["anzahl"] == 1
    finally:
        await collector.stop()


async def test_recording_starts_despite_failed_migration(clean, tmp_path, monkeypatch):
    import main

    app_pool, collector_pool = clean
    site = tmp_path / "anlage"
    site.mkdir()
    (site / "1000_kaputt.sql").write_text("SELECT gibt_es_nicht();", encoding="utf-8")
    original = migration_runner.discover
    monkeypatch.setattr(migration_runner, "discover", lambda *a, **k: original(site_dir=site))
    service = main.AdminService("", "test", start_backend=False)

    async def pools():
        service.app_pool, service.collector_pool = app_pool, collector_pool

    monkeypatch.setattr(service, "_connect_pools", pools)
    monkeypatch.setattr(main, "connection_settings", lambda: None)
    await service._start_backend_services()
    try:
        assert service.collector is not None and "1000_kaputt" in service.startup_error
        state = await service._collector_health()
        assert state.is_ok is False and "läuft mit dem bisherigen Schema" in state.detail
    finally:
        await service.collector.stop()
