#!/command/with-contenv bashio
# Gemeinsame Laufzeitwerte für alle Dienste festlegen.
# shellcheck source=/usr/lib/skytech/lib.sh
source /usr/lib/skytech/lib.sh

log_level=$(skytech::option log_level info)
bashio::log.level "${log_level}"

if skytech::has_supervisor; then
    ingress_entry=$(bashio::addon.ingress_entry)
else
    # Lokaler Test ohne Supervisor: Pfad frei wählbar, damit der Sub-Pfad von
    # Grafana auch ohne Home Assistant geprüft werden kann.
    ingress_entry="${SKYTECH_INGRESS_ENTRY:-/api/hassio_ingress/lokaltest}"
    bashio::log.warning "Kein Supervisor gefunden – lokaler Testbetrieb mit Ingress-Pfad ${ingress_entry}."
fi

# Der Supervisor liefert den Pfad ohne abschließenden Schrägstrich; darauf
# bauen nginx- und Grafana-Vorlage auf.
ingress_entry="${ingress_entry%/}"

install -d -m 755 "${SKYTECH_RUN_DIR}"
skytech::export_env SKYTECH_INGRESS_ENTRY "${ingress_entry}"
skytech::export_env SKYTECH_LOG_LEVEL "${log_level}"

# Interne Zugangsdaten, die kein Mensch eingeben muss: einmal erzeugt, in
# /data abgelegt (damit im Backup) und nie protokolliert.
install -d -m 700 /data/secrets
if [[ ! -s /data/secrets/grafana_db_password ]]; then
    (umask 077 && head -c 32 /dev/urandom | base64 | tr -d '\n/+=' > /data/secrets/grafana_db_password)
fi

# Wiederherstellung aus einem HA-Backup erkennen (D-023): das Backup enthält
# den Dump, aber kein Datenbankverzeichnis. Grafana bekommt dann seine
# konsistente Kopie zurück, die Datenbank spielt init-postgres ein.
if [[ -s /data/backup/ha_snapshot.dump ]]; then
    if [[ ! -s /data/pgdata/PG_VERSION ]]; then
        bashio::log.info "Wiederherstellung aus einem Home-Assistant-Backup erkannt."
        touch "${SKYTECH_RUN_DIR}/ha_restore"
        if [[ -s /data/backup/ha_snapshot_grafana.db ]]; then
            install -d /data/grafana
            cp /data/backup/ha_snapshot_grafana.db /data/grafana/grafana.db
        fi
    else
        # Überbleibsel eines Backups, dessen Nacharbeit nicht lief.
        rm -f /data/backup/ha_snapshot.dump /data/backup/ha_snapshot_grafana.db
    fi
fi

bashio::log.info "Skytech Data Insight ${SKYTECH_VERSION:-dev} startet."
