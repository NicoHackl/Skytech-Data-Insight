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

# Port 3000 optional per https mit dem HA-Zertifikat (D-026): ohne das lässt der
# Browser Grafana nicht in einer https-Seite von Home Assistant einbetten.
# Fehlen die Dateien, bleibt es bei http – der Start darf daran nicht scheitern.
grafana_listen="3000"
grafana_tls="        # Port 3000 unverschlüsselt"
if [[ "$(skytech::option grafana_tls false)" == "true" ]]; then
    cert_file="/ssl/$(basename "$(skytech::option grafana_tls_certfile fullchain.pem)")"
    key_file="/ssl/$(basename "$(skytech::option grafana_tls_keyfile privkey.pem)")"
    if [[ -r "${cert_file}" && -r "${key_file}" ]]; then
        grafana_listen="3000 ssl"
        grafana_tls="        ssl_certificate ${cert_file};
        ssl_certificate_key ${key_file};
        ssl_protocols TLSv1.2 TLSv1.3;"
        bashio::log.info "Grafana (Port 3000) wird per https ausgeliefert."
    else
        bashio::log.warning "grafana_tls ist an, aber ${cert_file} oder ${key_file} fehlt oder ist nicht lesbar – Port 3000 bleibt unverschlüsselt."
    fi
fi

skytech::render nginx.conf "${SKYTECH_RUN_DIR}/nginx/nginx.conf" \
    INGRESS_ENTRY="${SKYTECH_INGRESS_ENTRY}" \
    INGRESS_ACCESS="${ingress_access}" \
    GRAFANA_LISTEN="${grafana_listen}" \
    GRAFANA_TLS="${grafana_tls}"
