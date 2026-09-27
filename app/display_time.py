"""Für Menschen lesbare Zeitangaben (eiserne Regel 9 in AGENTS.md).

Maschinenformate bleiben ISO 8601 in UTC; alles, was ein Mensch liest, entsteht
hier als `TT.MM.JJJJ hh:mm:ss` in Berliner Zeit ohne Offset oder Kürzel.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")


def format_berlin(moment: datetime) -> str:
    """Formatiert einen Zeitpunkt als `TT.MM.JJJJ hh:mm:ss` in Berliner Zeit.

    Naive Zeitpunkte gelten als UTC – so speichert sie die Datenbank.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(BERLIN).strftime("%d.%m.%Y %H:%M:%S")
