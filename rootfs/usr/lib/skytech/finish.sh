#!/command/with-contenv bashio
# Gemeinsames Dienstende. s6 übergibt Dienstname, Exit-Code und Signal.
# Code 256 heißt „per Signal beendet" – das ist der reguläre Stopp des Add-ons.
# Jedes andere Ende eines Dienstes stoppt das ganze Add-on: ein halb laufendes
# Add-on (z. B. Grafana ohne Datenbank) sähe für HA gesund aus, der Watchdog
# startet es dagegen sauber neu.
readonly service="$1" exit_code="$2"

if [[ "${exit_code}" -ne 0 ]] && [[ "${exit_code}" -ne 256 ]]; then
    bashio::log.error "Dienst ${service} wurde unerwartet beendet (Code ${exit_code}). Das Add-on wird gestoppt."
    echo "${exit_code}" > /run/s6-linux-init-container-results/exitcode
    exec /run/s6/basedir/bin/halt
fi
