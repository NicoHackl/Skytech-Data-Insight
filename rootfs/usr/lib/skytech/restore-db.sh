#!/command/with-contenv bashio
# Stellt die Datenbank skytech aus einem pg_dump-Archiv (Format custom) wieder her.
# Aufruf: restore-db.sh <archiv>
#
# Voraussetzung: PostgreSQL läuft (Socket /run/postgresql), die Rollen existieren
# (bootstrap.sql). Ablauf nach TimescaleDB-Vorgabe: Datenbank neu anlegen,
# Erweiterung anlegen, timescaledb_pre_restore(), pg_restore, timescaledb_post_restore().
# Die bestehende Datenbank skytech wird dabei ersetzt – Aufrufer sichern vorher.
# shellcheck source=/usr/lib/skytech/lib.sh
source /usr/lib/skytech/lib.sh

readonly archive="$1"
readonly PGBIN="/usr/lib/postgresql/${PG_MAJOR}/bin"

if [[ ! -r "${archive}" ]]; then
    bashio::exit.nok "Sicherung ${archive} nicht lesbar."
fi

as_postgres() {
    PGOPTIONS="-c client_min_messages=warning" s6-setuidgid postgres "$@"
}
psql_postgres() {
    as_postgres "${PGBIN}/psql" --no-psqlrc --quiet --set=ON_ERROR_STOP=1 \
        --host=/run/postgresql --username=postgres "$@"
}

bashio::log.info "Stelle Datenbank aus $(basename "${archive}") wieder her …"

# Archiv vorab prüfen: ein kaputtes Archiv darf die bestehende Datenbank nicht ersetzen.
if ! as_postgres "${PGBIN}/pg_restore" --list "${archive}" > /dev/null 2>&1; then
    bashio::exit.nok "$(basename "${archive}") ist kein gültiges pg_dump-Archiv."
fi

psql_postgres --dbname=postgres --command="DROP DATABASE IF EXISTS skytech WITH (FORCE)"
psql_postgres --dbname=postgres --command="CREATE DATABASE skytech OWNER skytech_app ENCODING 'UTF8' TEMPLATE template0"
psql_postgres --dbname=skytech --command="CREATE EXTENSION IF NOT EXISTS timescaledb"
psql_postgres --dbname=skytech --command="SELECT timescaledb_pre_restore()" > /dev/null

# pg_restore meldet erwartbare Konflikte (Schema public, Erweiterung existiert
# bereits) als Fehler; entscheidend ist die Prüfung danach.
as_postgres "${PGBIN}/pg_restore" --dbname=skytech --host=/run/postgresql --username=postgres \
    --no-password "${archive}" 2> /run/skytech/restore.log || true

psql_postgres --dbname=skytech --command="SELECT timescaledb_post_restore()" > /dev/null
psql_postgres --dbname=skytech --file=/usr/share/skytech/bootstrap_skytech.sql

migrations=$(psql_postgres --dbname=skytech --tuples-only --no-align \
    --command="SELECT count(*) FROM skytech_config.migration" 2>/dev/null || echo 0)
if [[ "${migrations}" -lt 1 ]]; then
    tail -n 20 /run/skytech/restore.log
    bashio::exit.nok "Wiederherstellung unvollständig: Schema fehlt nach dem Einspielen."
fi

bashio::log.info "Datenbank wiederhergestellt (${migrations} Migration(en) im Stand)."
