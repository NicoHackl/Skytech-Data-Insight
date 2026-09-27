from datetime import datetime, timezone

from display_time import format_berlin


def test_summer_time_without_offset():
    assert format_berlin(datetime(2026, 7, 1, 10, 0, 5, tzinfo=timezone.utc)) == "01.07.2026 12:00:05"


def test_winter_time_without_offset():
    assert format_berlin(datetime(2026, 1, 15, 23, 30, tzinfo=timezone.utc)) == "16.01.2026 00:30:00"


def test_naive_timestamp_counts_as_utc():
    assert format_berlin(datetime(2026, 9, 27, 11, 0)) == "27.09.2026 13:00:00"
