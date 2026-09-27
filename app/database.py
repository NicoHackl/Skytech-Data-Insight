"""Verbindungen zur Datenbank.

Zwei Pools mit getrennten Rollen (D-012, docs/datenmodell.md):
- `app`: Besitzer der Objekte – Migrationen, Sensorverwaltung, Status.
- `collector`: darf nur Messwerte schreiben und Sensoren lesen.

Im Add-on geht alles über den Unix-Socket mit `peer`-Anmeldung. Für Tests
lassen sich Host, Port und Passwort per Umgebung setzen.
"""

import os

import asyncpg

DATABASE = "skytech"
APP_ROLE = "skytech_app"
COLLECTOR_ROLE = "skytech_collector"


def connection_options(role: str) -> dict:
    """Verbindungsparameter für eine Rolle."""
    options = {
        "host": os.environ.get("SKYTECH_DB_HOST", "/run/postgresql"),
        "port": int(os.environ.get("SKYTECH_DB_PORT", "5432")),
        "database": os.environ.get("SKYTECH_DB_NAME", DATABASE),
        "user": role,
        # Alle Zeitstempel als UTC an Python – umgerechnet wird erst in der Anzeige.
        "server_settings": {"timezone": "UTC", "application_name": f"skytech-{role}"},
    }
    password = os.environ.get("SKYTECH_DB_TEST_PASSWORD")
    if password:
        options["password"] = password
    return options


async def create_pool(role: str, max_size: int = 4) -> asyncpg.Pool:
    """Legt einen Pool für die Rolle an."""
    return await asyncpg.create_pool(min_size=1, max_size=max_size, timeout=10, **connection_options(role))
