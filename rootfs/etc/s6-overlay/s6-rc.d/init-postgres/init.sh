#!/command/with-contenv bashio
# Datenbank-Cluster anlegen (erster Start), Laufzeitkonfiguration schreiben und
# die Grundobjekte sicherstellen. Läuft bei jedem Start und ist idempotent.
# shellcheck source=/usr/lib/skytech/lib.sh
source /usr/lib/skytech/lib.sh

readonly PGBIN="/usr/lib/postgresql/${PG_MAJOR}/bin"
readonly PGDATA="/data/pgdata"
readonly PGRUN="${SKYTECH_RUN_DIR}/postgres"

install -d -o postgres -g postgres -m 2775 /run/postgresql
install -d -o postgres -g postgres -m 755 "${PGRUN}"
skytech::render postgresql.conf "${PGRUN}/skytech.conf" RUN_DIR="${PGRUN}"
skytech::render pg_hba.conf "${PGRUN}/pg_hba.conf"
skytech::render pg_ident.conf "${PGRUN}/pg_ident.conf"

if [[ ! -s "${PGDATA}/PG_VERSION" ]]; then
    bashio::log.info "Kein Datenbank-Cluster vorhanden – lege ihn unter ${PGDATA} an."
    install -d -o postgres -g postgres -m 700 "${PGDATA}"
    s6-setuidgid postgres "${PGBIN}/initdb" \
        --pgdata="${PGDATA}" \
        --username=postgres \
        --encoding=UTF8 \
        --locale=C.UTF-8 \
        --auth-local=peer \
        --auth-host=scram-sha-256 \
        > /dev/null
    # Alle Einstellungen des Add-ons kommen aus der bei jedem Start neu
    # geschriebenen Datei; die Vorgaben von initdb bleiben unangetastet.
    echo "include_if_exists = '${PGRUN}/skytech.conf'" >> "${PGDATA}/postgresql.conf"
fi

cluster_major=$(<"${PGDATA}/PG_VERSION")
if [[ "${cluster_major}" != "${PG_MAJOR}" ]]; then
    bashio::exit.nok "Der Datenbank-Cluster stammt von PostgreSQL ${cluster_major}, das Add-on bringt ${PG_MAJOR} mit. Ein Wechsel der Hauptversion geht nur über Sicherung und Wiederherstellung."
fi

# Nach einer Wiederherstellung können Besitzrechte abweichen.
chown postgres:postgres "${PGDATA}"
chmod 700 "${PGDATA}"

# Grundobjekte anlegen: dafür den Server kurz nur über den lokalen Socket starten.
if ! s6-setuidgid postgres "${PGBIN}/pg_ctl" --pgdata="${PGDATA}" \
        --options="-c listen_addresses=''" --log="${PGRUN}/bootstrap.log" \
        --wait --timeout=300 start > /dev/null; then
    cat "${PGRUN}/bootstrap.log"
    bashio::exit.nok "Datenbank ließ sich für die Grundeinrichtung nicht starten."
fi

bootstrap_ok=true
psql_run() {
    # NOTICE-Meldungen wie „extension already exists" sind im Normalfall erwartet.
    PGOPTIONS="-c client_min_messages=warning" s6-setuidgid postgres "${PGBIN}/psql" --no-psqlrc --quiet --set=ON_ERROR_STOP=1 \
        --host=/run/postgresql --username=postgres "$@"
}
psql_run --dbname=postgres --file=/usr/share/skytech/bootstrap.sql || bootstrap_ok=false
# Eigene Sitzung für das Update: TimescaleDB verlangt, dass ALTER EXTENSION
# der erste Befehl nach dem Verbinden ist.
if [[ "${bootstrap_ok}" == true ]]; then
    psql_run --dbname=skytech --command="CREATE EXTENSION IF NOT EXISTS timescaledb" || bootstrap_ok=false
fi
if [[ "${bootstrap_ok}" == true ]]; then
    psql_run --dbname=skytech --command="ALTER EXTENSION timescaledb UPDATE" || bootstrap_ok=false
fi

s6-setuidgid postgres "${PGBIN}/pg_ctl" --pgdata="${PGDATA}" --mode=fast --wait stop > /dev/null

if [[ "${bootstrap_ok}" != true ]]; then
    bashio::exit.nok "Grundeinrichtung der Datenbank fehlgeschlagen (Details im Protokoll oberhalb)."
fi
bashio::log.info "Datenbank bereit."
