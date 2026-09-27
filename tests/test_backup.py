import os
import time

import backup
from mcp_tools import next_site_migration_number, to_json_value


def test_prune_keeps_newest(tmp_path):
    for index in range(5):
        (tmp_path / f"mcp_2026092{index}_000000_000000.dump").write_bytes(b"x")
    (tmp_path / "manuell_20260101_000000_000000.dump").write_bytes(b"x")
    removed = backup.prune("mcp", tmp_path, keep=2)
    assert sorted(removed) == [f"mcp_2026092{i}_000000_000000.dump" for i in range(3)]
    assert len(list(tmp_path.glob("*.dump"))) == 3


def test_list_backups_newest_first(tmp_path):
    old = tmp_path / "manuell_20260101_000000.dump"
    new = tmp_path / "mcp_20260102_000000_1.dump"
    (tmp_path / "fremd.txt").write_text("x")
    old.write_bytes(b"1")
    new.write_bytes(b"22")
    past = time.time() - 100
    os.utime(old, (past, past))
    listed = backup.list_backups(tmp_path)
    assert [item.name for item in listed] == [new.name, old.name]
    assert listed[0].to_json()["art_text"] == "Vor MCP-Änderung"
    assert backup.list_backups(tmp_path / "fehlt") == []


def test_dump_command_runs_as_postgres_when_root(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    assert backup.dump_command(tmp_path / "x.dump")[:3] == ["s6-setuidgid", "postgres", "pg_dump"]


def test_site_migration_numbers():
    assert next_site_migration_number([1]) == 1000
    assert next_site_migration_number([1, 1000, 1003]) == 1004


def test_json_values():
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal
    assert to_json_value(Decimal("1.5")) == 1.5
    assert to_json_value(timedelta(minutes=1)) == 60.0
    assert to_json_value(datetime(2026, 9, 27, tzinfo=timezone.utc)) == "2026-09-27T00:00:00+00:00"
    assert to_json_value({"a": [Decimal("2")]}) == {"a": [2.0]}


def test_resolve_rejects_paths_and_unknown_names(tmp_path):
    import pytest
    (tmp_path / "manuell_20260101_000000.dump").write_bytes(b"x")
    assert backup.resolve("manuell_20260101_000000.dump", tmp_path).exists()
    for name in ("../etc/passwd", "manuell_20260101_000000.dump/../x", "fremd.txt", "manuell_20990101_000000.dump"):
        with pytest.raises(backup.BackupError):
            backup.resolve(name, tmp_path)


def test_state_roundtrip(tmp_path):
    assert backup.read_state(tmp_path) is None
    backup.write_state({"status": "laeuft"}, tmp_path)
    assert backup.read_state(tmp_path) == {"status": "laeuft"}


async def test_inspect_archive_and_bad_tar(tmp_path):
    import io
    import json
    import tarfile
    import pytest
    archive = tmp_path / "upload_20260101_000000.tar"
    with tarfile.open(archive, "w") as tar:
        for name, data in (("datenbank.dump", b"PGDMP"), ("sicherung.json", json.dumps({"version": "0.4.0"}).encode())):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    info = await backup.inspect(archive)
    assert info["beschreibung"] == {"version": "0.4.0"} and info["grafana"] is False
    broken = tmp_path / "upload_20260101_000001.tar"
    broken.write_bytes(b"kein tar")
    with pytest.raises(backup.BackupError):
        await backup.inspect(broken)


def test_grafana_copy(tmp_path):
    import sqlite3
    source = tmp_path / "grafana.db"
    connection = sqlite3.connect(source)
    connection.execute("CREATE TABLE t (x)")
    connection.execute("INSERT INTO t VALUES (1)")
    connection.commit()
    connection.close()
    assert backup.copy_grafana_db(tmp_path / "kopie.db", source)
    assert sqlite3.connect(tmp_path / "kopie.db").execute("SELECT x FROM t").fetchone() == (1,)
    assert not backup.copy_grafana_db(tmp_path / "x.db", tmp_path / "fehlt.db")


async def test_restorer_order_and_failure(tmp_path, monkeypatch):
    calls = []

    async def fake_create(prefix, directory=None):
        calls.append(("sicherung", prefix))
        return backup.BackupFile(f"{prefix}_20260101_000000.dump", 1, backup.datetime.now(backup.timezone.utc))

    async def fake_run(command, timeout):
        calls.append(("run", command[0]))
        return (1, "FEHLER: kaputt") if "restore-db" in command[0] else (0, "")

    async def before():
        calls.append(("stopp",))

    monkeypatch.setattr(backup, "create", fake_create)
    source = tmp_path / "manuell_20260101_000000.dump"
    source.write_bytes(b"x")
    restorer = backup.Restorer(directory=tmp_path, run=fake_run)
    state = await restorer.restore(source, "nico", before)
    assert calls == [("sicherung", "vor_wiederherstellung"), ("stopp",), ("run", "/usr/lib/skytech/restore-db.sh")]
    assert state["status"] == "fehlgeschlagen" and "kaputt" in state["meldung"]
    assert backup.read_state(tmp_path)["status"] == "fehlgeschlagen"
    assert not restorer.busy


def test_unpack_only_known_members(tmp_path):
    import io
    import tarfile
    archive = tmp_path / "upload_20260101_000000.tar"
    with tarfile.open(archive, "w") as tar:
        for name, data in (("datenbank.dump", b"PGDMP"), ("grafana.db", b"SQLite"), ("../boese.txt", b"x")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    work = tmp_path / "work"
    dump, grafana = backup.Restorer(directory=tmp_path)._unpack(archive, work)
    assert dump.read_bytes() == b"PGDMP" and grafana.read_bytes() == b"SQLite"
    assert not (tmp_path / "boese.txt").exists()
