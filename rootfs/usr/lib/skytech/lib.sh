#!/usr/bin/env bash
# Gemeinsame Helfer der Init- und Dienstskripte. Wird per `source` eingebunden.
#
# Optionen werden direkt aus /data/options.json gelesen statt über
# bashio::config: so laufen die Skripte auch im lokalen Container-Test ohne
# Supervisor (docs/test-strategie.md). Der Supervisor schreibt die Datei vor
# jedem Start; das Add-on liest sie nur.

readonly SKYTECH_OPTIONS_FILE="/data/options.json"
# shellcheck disable=SC2034  # wird von den einbindenden Skripten genutzt
readonly SKYTECH_RUN_DIR="/run/skytech"
readonly SKYTECH_TEMPLATE_DIR="/usr/share/skytech/templates"

# Wert einer Add-on-Option, sonst der übergebene Default.
skytech::option() {
    local key="$1" default="${2:-}" value=""
    if [[ -f "${SKYTECH_OPTIONS_FILE}" ]]; then
        value=$(jq -r --arg key "${key}" '.[$key] // empty' "${SKYTECH_OPTIONS_FILE}")
    fi
    if [[ -z "${value}" ]]; then
        printf '%s' "${default}"
    else
        printf '%s' "${value}"
    fi
}

# Läuft der Container unter dem Supervisor (und nicht im lokalen Test)?
skytech::has_supervisor() {
    [[ -n "${SUPERVISOR_TOKEN:-}" ]]
}

# Macht eine Variable für alle Dienste sichtbar, die mit `with-contenv` starten.
skytech::export_env() {
    printf '%s' "$2" > "/run/s6/container_environment/$1"
}

# Ersetzt Platzhalter der Form __NAME__ in einer Vorlage. Aufruf:
#   skytech::render <vorlage> <ziel> NAME=wert ...
# Werte dürfen kein `|` enthalten; Secrets gehören nie in eine Vorlage.
skytech::render() {
    local template="${SKYTECH_TEMPLATE_DIR}/$1" target="$2" pair key value content
    shift 2
    content=$(<"${template}")
    for pair in "$@"; do
        key="${pair%%=*}"
        value="${pair#*=}"
        content="${content//__${key}__/${value}}"
    done
    if [[ "${content}" =~ __[A-Z_]+__ ]]; then
        bashio::exit.nok "Vorlage $1: Platzhalter ${BASH_REMATCH[0]} wurde nicht ersetzt."
    fi
    install -d "$(dirname "${target}")"
    printf '%s\n' "${content}" > "${target}"
}
