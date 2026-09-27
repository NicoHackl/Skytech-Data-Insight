ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-debian:bookworm
FROM ${BUILD_FROM}

# Versionen bewusst gepinnt (docs/architektur.md). Das TimescaleDB-Paket ist je
# PostgreSQL-Minor gebaut (Suffix 1711 = PostgreSQL 17.11); beim Anheben beide
# Werte zusammen ändern. Ein Major-Wechsel von PostgreSQL braucht Dump/Restore.
ARG PG_MAJOR=17
ARG TIMESCALEDB_VERSION=2.30.1~debian12-1711
ARG GRAFANA_VERSION=13.2.2
ARG BUILD_VERSION=dev

ENV LANG=C.UTF-8 \
    PG_MAJOR=${PG_MAJOR} \
    SKYTECH_VERSION=${BUILD_VERSION} \
    # Postgres und Grafana brauchen beim Stopp länger als die s6-Voreinstellung von 3 s.
    S6_SERVICES_GRACETIME=30000 \
    S6_KILL_GRACETIME=5000 \
    S6_CMD_WAIT_FOR_SERVICES_MAXTIME=0

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends gnupg ca-certificates \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/pgdg.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && curl -fsSL https://packagecloud.io/timescale/timescaledb/gpgkey | gpg --dearmor -o /usr/share/keyrings/timescale.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/timescale.gpg] https://packagecloud.io/timescale/timescaledb/debian/ bookworm main" > /etc/apt/sources.list.d/timescale.list \
    && curl -fsSL https://apt.grafana.com/gpg.key | gpg --dearmor -o /usr/share/keyrings/grafana.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/grafana.gpg] https://apt.grafana.com stable main" > /etc/apt/sources.list.d/grafana.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        "postgresql-${PG_MAJOR}" \
        "timescaledb-2-postgresql-${PG_MAJOR}=${TIMESCALEDB_VERSION}" \
        "timescaledb-2-loader-postgresql-${PG_MAJOR}=${TIMESCALEDB_VERSION}" \
        "grafana=${GRAFANA_VERSION}" \
        nginx \
        python3 \
        python3-venv \
    # Debian legt beim Paket-Install einen eigenen Cluster an; das Add-on
    # verwaltet seinen Cluster selbst unter /data/pgdata.
    && rm -rf /var/lib/postgresql/* /etc/postgresql/* \
    && rm -f /etc/nginx/sites-enabled/default \
    && apt-get purge -y gnupg \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY app/requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY rootfs /
COPY app /opt/skytech/app
COPY grafana/provisioning /etc/grafana/provisioning

# Ausführbar-Bits unabhängig davon setzen, ob der Checkout sie erhalten hat.
RUN find /etc/s6-overlay/s6-rc.d -type f \( -name run -o -name finish -o -name init.sh \) -exec chmod +x {} + \
    && chmod +x /usr/lib/skytech/*.sh

LABEL \
    io.hass.name="Skytech Data Insight" \
    io.hass.type="addon" \
    io.hass.arch="amd64" \
    io.hass.version="${BUILD_VERSION}"
