"""Name und HA-Konfigurationsseite des eigenen Add-ons für den Sidebar-Fuß (D-028).

Der Slug trägt das Präfix des Add-on-Repositorys (z. B.
`e778e1d3_skytech_data_insight`) und steht nur beim Supervisor. Ohne ihn gibt es
keinen Link – der Fuß zeigt dann nur den Namen.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from supervisor_client import SupervisorClient, SupervisorRejected, SupervisorUnavailable

log = logging.getLogger(__name__)

FALLBACK_NAME = "Skytech Data Insight"

# Supervisor-Slugs bestehen aus Kleinbuchstaben, Ziffern und Unterstrichen. Was
# anders aussieht, wird nicht zu einem Pfad im HA-Frontend zusammengesetzt.
_SLUG_PATTERN = re.compile(r"[a-z0-9_]+")


def fallback() -> dict[str, Any]:
    """Antwort ohne Supervisor: Name ohne Link."""
    return {"name": FALLBACK_NAME, "config_path": None}


async def fetch(supervisor: SupervisorClient) -> dict[str, Any] | None:
    """Liest Name und Slug beim Supervisor. `None`, wenn das nicht gelingt."""
    if not supervisor.available:
        return None
    try:
        info = await supervisor.self_info()
    except (SupervisorUnavailable, SupervisorRejected) as exc:
        log.warning("Add-on-Slug nicht abrufbar, Sidebar-Fuß ohne Link: %s", exc)
        return None
    slug = str(info.get("slug") or "")
    if not _SLUG_PATTERN.fullmatch(slug):
        log.warning("Supervisor meldet keinen gültigen Add-on-Slug, Sidebar-Fuß ohne Link.")
        return None
    return {
        "name": str(info.get("name") or FALLBACK_NAME),
        "config_path": f"/hassio/addon/{slug}/config",
    }
