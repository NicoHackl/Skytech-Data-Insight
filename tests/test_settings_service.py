"""Aufbewahrung: Prüfung der Eingaben und API-Antworten ohne Datenbank."""

import pytest
from aiohttp.test_utils import TestClient, TestServer

import main
import settings_service


def test_validate_retention_accepts_days_and_never():
    assert settings_service.validate_retention(365, None) == (365, None)
    assert settings_service.validate_retention(None, 31) == (None, 31)


@pytest.mark.parametrize("raw, minute, field", [
    (0, None, "rohwerte_tage"),
    (365, 30, "minutenwerte_tage"),
    ("365", None, "rohwerte_tage"),
    (True, None, "rohwerte_tage"),
    (1.5, None, "rohwerte_tage"),
])
def test_validate_retention_rejects(raw, minute, field):
    with pytest.raises(settings_service.RetentionError) as error:
        settings_service.validate_retention(raw, minute)
    assert field in error.value.field_errors


async def test_retention_api_validates_before_database():
    service = main.AdminService(ingress_entry="", version="test", start_backend=False)
    async with TestClient(TestServer(service.build_app())) as client:
        missing = await client.put("/api/retention", json={"rohwerte_tage": 365})
        assert missing.status == 400
        invalid = await client.put("/api/retention", json={"rohwerte_tage": 365, "minutenwerte_tage": 7})
        assert invalid.status == 422
        assert "minutenwerte_tage" in (await invalid.json())["field_errors"]
        # Gültig, aber ohne Datenbank: 503 statt still nichts zu tun.
        valid = await client.put("/api/retention", json={"rohwerte_tage": 365, "minutenwerte_tage": None})
        assert valid.status == 503
