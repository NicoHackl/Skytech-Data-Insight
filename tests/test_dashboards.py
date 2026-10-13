"""Versionierte Grafana-Dashboards unter grafana/dashboards/.

Struktur immer; die SQL-Abfragen jedes Panels zusätzlich gegen eine frisch
migrierte TimescaleDB, wenn `SKYTECH_TEST_DSN` gesetzt ist. So fällt auf, wenn
eine Migration eine Spalte oder Sicht ändert, die ein Dashboard benutzt.
"""

import asyncio
import json
import os
import re
from pathlib import Path

import asyncpg
import pytest

import migration_runner

DASHBOARDS = sorted((Path(__file__).resolve().parent.parent / "grafana" / "dashboards").glob("*.json"))
DATASOURCE = {"type": "grafana-postgresql-datasource", "uid": "skytech-db"}
DSN = os.environ.get("SKYTECH_TEST_DSN")
TEST_DB = "skytech_dashboard_test"


def _targets(dashboard):
    for panel in dashboard["panels"]:
        for target in panel.get("targets", []):
            yield panel, target
    for annotation in dashboard["annotations"]["list"]:
        yield {"title": f"Anmerkung {annotation['name']}"}, annotation["target"]
    for variable in dashboard["templating"]["list"]:
        if variable["type"] == "query":
            yield {"title": f"Variable {variable['name']}"}, {"rawSql": variable["query"]}


def _executable(sql: str) -> str:
    """Grafana-Makros und Variablen durch feste Werte ersetzen, wie es Grafana zur Laufzeit tut."""
    sql = re.sub(r"\$__timeFilter\(([^)]+)\)",
                 r"\1 BETWEEN now() - interval '1 day' AND now() + interval '1 day'", sql)
    replacements = {"$netz_sensor": "1", "$netz_vorzeichen": "1", "$speicher_kwh": "10", "$wirkungsgrad": "0.85"}
    for name, value in replacements.items():
        sql = sql.replace(name, value)
    assert not re.search(r"\$_*[A-Za-z]", sql), f"Unbekannte Variable oder Makro in: {sql[:120]}"
    return sql


def test_dashboards_exist():
    assert [path.name for path in DASHBOARDS] == ["skytech-dynamischer-strompreis.json"]


@pytest.mark.parametrize("path", DASHBOARDS, ids=lambda path: path.stem)
def test_dashboard_structure(path):
    dashboard = json.loads(path.read_text())
    assert dashboard["uid"] == path.stem and dashboard["title"]
    assert dashboard["timezone"] == "Europe/Berlin"
    ids = [panel["id"] for panel in dashboard["panels"]]
    assert len(ids) == len(set(ids))
    for panel in dashboard["panels"]:
        position = panel["gridPos"]
        assert position["x"] + position["w"] <= 24
        if panel["type"] not in ("row", "text"):
            assert panel["datasource"] == DATASOURCE, panel["title"]
            assert panel["targets"], panel["title"]
    for panel, target in _targets(dashboard):
        if "datasource" in target:
            assert target["datasource"] == DATASOURCE, panel["title"]
        assert "skytech." in target["rawSql"] or "now()" in target["rawSql"], panel["title"]


@pytest.mark.skipif(not DSN, reason="SKYTECH_TEST_DSN nicht gesetzt – keine TimescaleDB für Integrationstests")
@pytest.mark.parametrize("path", DASHBOARDS, ids=lambda path: path.stem)
def test_dashboard_queries_run_against_migrated_schema(path):
    dashboard = json.loads(path.read_text())

    async def run():
        admin = await asyncpg.connect(DSN)
        try:
            for role in ("skytech_app", "skytech_collector", "skytech_admin", "skytech_reader", "skytech_hems"):
                if not await admin.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", role):
                    await admin.execute(f"CREATE ROLE {role} LOGIN")
            await admin.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
            await admin.execute(f"CREATE DATABASE {TEST_DB} OWNER skytech_app")
        finally:
            await admin.close()
        dsn = f"{DSN.rpartition('/')[0]}/{TEST_DB}"
        superuser = await asyncpg.connect(dsn)
        await superuser.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
        await superuser.close()
        app = await asyncpg.connect(dsn, server_settings={"role": "skytech_app", "timezone": "UTC"})
        try:
            await migration_runner.migrate(app, migration_runner.discover(site_dir=Path("/nonexistent")))
        finally:
            await app.close()
        # Lesen wie Grafana: Rolle skytech_reader (skytech_grafana erbt sie).
        reader = await asyncpg.connect(dsn, server_settings={"role": "skytech_reader", "timezone": "UTC"})
        failures = []
        try:
            for panel, target in _targets(dashboard):
                try:
                    await reader.fetch(_executable(target["rawSql"]))
                except asyncpg.PostgresError as exc:
                    failures.append(f"{panel['title']}: {exc}")
        finally:
            await reader.close()
        admin = await asyncpg.connect(DSN)
        await admin.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        await admin.close()
        assert failures == []

    asyncio.run(run())
