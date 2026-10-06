"""Konsistenz von Add-on-Manifest, Übersetzungen, s6-Diensten und Vorlagen."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
S6 = ROOT / "rootfs/etc/s6-overlay/s6-rc.d"
TEMPLATES = ROOT / "rootfs/usr/share/skytech/templates"


def _manifest() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def test_manifest_basics():
    manifest = _manifest()
    assert manifest["slug"] == "skytech_data_insight"
    assert manifest["arch"] == ["amd64"]
    # s6-overlay v3 aus dem Basis-Image braucht init: false.
    assert manifest["init"] is False
    assert manifest["ingress"] is True
    assert manifest["ingress_port"] == 8099
    assert re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"])


def test_every_option_has_schema_and_translations():
    manifest = _manifest()
    options = set(manifest["options"])
    assert options == set(manifest["schema"])
    for language in ("de", "en"):
        translation = yaml.safe_load((ROOT / f"translations/{language}.yaml").read_text(encoding="utf-8"))
        assert set(translation["configuration"]) == options, language
        assert set(translation["network"]) == set(manifest["ports"]), language


def test_every_service_is_in_user_bundle_and_dependencies_exist():
    bundle = {path.name for path in (S6 / "user/contents.d").iterdir()}
    services = {path.name for path in S6.iterdir() if path.name != "user"}
    assert bundle == services
    for service in services:
        for dependency in (S6 / service / "dependencies.d").iterdir():
            assert dependency.name == "base" or dependency.name in services, (service, dependency.name)


def test_oneshots_point_to_existing_script_and_longruns_have_run():
    for service in S6.iterdir():
        if service.name == "user":
            continue
        kind = (service / "type").read_text().strip()
        if kind == "oneshot":
            script = (service / "up").read_text().strip()
            assert script == f"/etc/s6-overlay/s6-rc.d/{service.name}/init.sh"
            assert (service / "init.sh").exists()
        else:
            assert kind == "longrun"
            assert (service / "run").exists() and (service / "finish").exists()


def test_every_template_placeholder_is_rendered():
    """Jeder Platzhalter einer Vorlage wird vom zugehörigen Init-Skript gesetzt."""
    scripts = "\n".join(path.read_text(encoding="utf-8") for path in S6.glob("*/init.sh"))
    # Fortgesetzte Zeilen zusammenziehen, damit ein Aufruf eine Zeile ist.
    scripts = scripts.replace("\\\n", " ")
    for template in TEMPLATES.iterdir():
        placeholders = set(re.findall(r"__([A-Z_]+)__", template.read_text(encoding="utf-8")))
        call = re.search(rf"skytech::render {re.escape(template.name)} [^\n]*", scripts)
        assert call, f"{template.name} wird nirgends gerendert"
        provided = set(re.findall(r"([A-Z_]+)=", call.group(0)))
        assert placeholders <= provided, (template.name, placeholders - provided)


def test_ingress_server_is_locked_to_supervisor():
    script = (S6 / "init-nginx/init.sh").read_text(encoding="utf-8")
    assert "allow 172.30.32.2; deny all;" in script
    nginx = (TEMPLATES / "nginx.conf").read_text(encoding="utf-8")
    # Der LAN-Server darf den Anmelde-Header nie durchreichen.
    lan = nginx.split("listen __GRAFANA_LISTEN__;", 1)[1]
    assert 'proxy_set_header X-WEBAUTH-USER "";' in lan


def test_access_page_requirements():
    """Seite „Zugänge“ (D-025): Rolle für das Schreiben der eigenen Optionen,
    SQL-Datei für Passwörter, lokale Sicherungen vor Änderungen nicht im HA-Backup."""
    manifest = _manifest()
    assert manifest["hassio_role"] == "manager"
    assert "backup/vor_aenderung_*" in manifest["backup_exclude"]
    sql = (ROOT / "rootfs/usr/share/skytech/set_password.sql").read_text(encoding="utf-8")
    assert "\\getenv password SKYTECH_PASSWORD" in sql and "%L" in sql
