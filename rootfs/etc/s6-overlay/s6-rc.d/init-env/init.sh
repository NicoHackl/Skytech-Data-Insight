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

bashio::log.info "Skytech Data Insight ${SKYTECH_VERSION:-dev} startet."
