#!/command/with-contenv bashio
# nginx-Konfiguration aus der Vorlage schreiben.
# shellcheck source=/usr/lib/skytech/lib.sh
source /usr/lib/skytech/lib.sh

# Der Ingress-Port darf nur vom Supervisor erreicht werden: er meldet den
# HA-Benutzer per Header an, und dieser Header wird an Grafana weitergereicht
# (D-006). Im lokalen Test ohne Supervisor entfällt die Sperre.
if skytech::has_supervisor; then
    ingress_access="allow 172.30.32.2; deny all;"
else
    ingress_access="# lokaler Testbetrieb: keine Zugriffssperre"
fi

skytech::render nginx.conf "${SKYTECH_RUN_DIR}/nginx/nginx.conf" \
    INGRESS_ENTRY="${SKYTECH_INGRESS_ENTRY}" \
    INGRESS_ACCESS="${ingress_access}"
