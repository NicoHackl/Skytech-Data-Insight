from datetime import datetime, timedelta, timezone

from collector import Collector, SensorConfig, extract
from values import StoredValue

T0 = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)


def state(value, changed=T0, updated=None, **attributes):
    return {
        "entity_id": "sensor.pv",
        "state": value,
        "attributes": attributes,
        "last_changed": changed.isoformat(),
        "last_updated": (updated or changed).isoformat(),
    }


def make_collector(*sensors):
    collector = Collector(None, None)
    collector._sensors = {s.id: s for s in sensors}
    collector._by_entity = {}
    for sensor in sensors:
        if sensor.active:
            collector._by_entity.setdefault(sensor.entity_id, []).append(sensor)
    return collector


def test_extract_state_uses_last_changed_attribute_uses_last_updated():
    later = T0 + timedelta(minutes=5)
    moment, value = extract(SensorConfig(1, "sensor.pv", None, True), state("100", T0, later))
    assert (moment, value) == (T0, StoredValue(100.0, None))
    moment, value = extract(SensorConfig(2, "sensor.pv", "temp", True), state("100", T0, later, temp=21))
    assert (moment, value) == (later, StoredValue(21.0, None))


def test_only_real_changes_are_buffered():
    collector = make_collector(SensorConfig(1, "sensor.pv", None, True))
    collector.on_state_changed(state("100", T0))
    # Attributänderung ohne Zustandswechsel: gleicher Wert, kein neuer Rohwert.
    collector.on_state_changed(state("100", T0, T0 + timedelta(seconds=5)))
    collector.on_state_changed(state("200", T0 + timedelta(seconds=10)))
    assert [(r.time, r.value.number) for r in collector._buffer] == [
        (T0, 100.0), (T0 + timedelta(seconds=10), 200.0),
    ]


def test_state_and_attribute_sensors_of_same_entity():
    collector = make_collector(SensorConfig(1, "sensor.pv", None, True), SensorConfig(2, "sensor.pv", "temp", True))
    collector.on_state_changed(state("100", T0, temp=20))
    collector.on_state_changed(state("100", T0, T0 + timedelta(seconds=30), temp=21))
    assert [(r.sensor_id, r.value.number) for r in collector._buffer] == [(1, 100.0), (2, 20.0), (2, 21.0)]


def test_inactive_and_foreign_sensors_are_ignored():
    collector = make_collector(SensorConfig(1, "sensor.pv", None, False))
    collector.on_state_changed(state("100"))
    collector.on_state_changed({**state("5"), "entity_id": "sensor.other"})
    assert not collector._buffer


def test_older_value_never_overwrites_newer():
    collector = make_collector(SensorConfig(1, "sensor.pv", None, True))
    collector.on_state_changed(state("100", T0))
    collector.on_state_changed(state("50", T0 - timedelta(seconds=1)))
    assert len(collector._buffer) == 1


def test_late_value_marks_recompute_but_not_older_than_limit():
    collector = make_collector(SensorConfig(1, "sensor.pv", None, True))
    collector._watermark = T0 + timedelta(hours=5)
    collector.on_state_changed(state("100", T0))
    assert collector._late == {1: T0 + timedelta(hours=4)}


def test_buffer_overflow_drops_oldest(monkeypatch):
    import collector as collector_module
    monkeypatch.setattr(collector_module, "MAX_BUFFER", 2)
    collector = make_collector(SensorConfig(1, "sensor.pv", None, True))
    for second in range(4):
        collector.on_state_changed(state(str(second), T0 + timedelta(seconds=second)))
    assert [r.value.number for r in collector._buffer] == [2.0, 3.0]
    assert collector.dropped == 2
