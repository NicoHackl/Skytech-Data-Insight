#!/command/with-contenv bashio
# Grafana-Konfiguration schreiben und das Admin-Passwort setzen.
# shellcheck source=/usr/lib/skytech/lib.sh
source /usr/lib/skytech/lib.sh

readonly GRAFANA_HOME="/usr/share/grafana"
readonly GRAFANA_CONFIG="${SKYTECH_RUN_DIR}/grafana/grafana.ini"

# Grafana protokolliert auf „info" sehr ausführlich; erst ab „debug" des
# Add-ons wird es gesprächig.
install -d -o grafana -g grafana -m 750 /data/grafana /data/grafana/plugins /data/grafana/log
skytech::render grafana.ini "${GRAFANA_CONFIG}" \
    INGRESS_ENTRY="${SKYTECH_INGRESS_ENTRY}" \
    GRAFANA_LOG_LEVEL="$(case "${SKYTECH_LOG_LEVEL}" in debug) echo debug ;; error) echo error ;; *) echo warn ;; esac)"
chmod 644 "${GRAFANA_CONFIG}"

# Das Passwort gilt nur für die Anmeldung im LAN; über Ingress meldet der
# Auth-Proxy an (D-006). Ohne gesetztes Passwort bekommt „admin" bei jedem
# Start ein neues Zufallspasswort – die LAN-Anmeldung ist dann gesperrt,
# statt mit dem Grafana-Standard „admin/admin" offenzustehen.
admin_password=$(skytech::option grafana_admin_password)
if [[ -z "${admin_password}" ]]; then
    admin_password=$(head -c 32 /dev/urandom | base64 | tr -d '\n/+=')
    bashio::log.info "Kein Grafana-Admin-Passwort gesetzt – Anmeldung im LAN ist gesperrt."
fi

if ! printf '%s' "${admin_password}" | s6-setuidgid grafana grafana cli \
        --homepath "${GRAFANA_HOME}" --config "${GRAFANA_CONFIG}" \
        admin reset-admin-password --password-from-stdin > "${SKYTECH_RUN_DIR}/grafana/cli.log" 2>&1; then
    cat "${SKYTECH_RUN_DIR}/grafana/cli.log"
    bashio::exit.nok "Grafana-Admin-Passwort ließ sich nicht setzen."
fi
