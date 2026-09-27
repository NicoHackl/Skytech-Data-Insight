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
    old = tmp_path / "a.dump"
    new = tmp_path / "b.dump"
    old.write_bytes(b"1")
    new.write_bytes(b"22")
    past = time.time() - 100
    os.utime(old, (past, past))
    assert [item.name for item in backup.list_backups(tmp_path)] == ["b.dump", "a.dump"]
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
