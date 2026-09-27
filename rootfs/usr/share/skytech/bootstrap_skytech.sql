-- Rechte innerhalb der Datenbank skytech, die nur der Superuser setzen kann.
-- Läuft bei jedem Start nach bootstrap.sql; idempotent.

-- Was skytech_admin (z. B. aus VSCode) neu anlegt, darf skytech_reader lesen.
-- Für Objekte von skytech_app setzt das die Migration 0001 selbst.
ALTER DEFAULT PRIVILEGES FOR ROLE skytech_admin GRANT SELECT ON TABLES TO skytech_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE skytech_admin GRANT USAGE ON SCHEMAS TO skytech_reader;

-- Die Anmelderollen dürfen sich nur mit dieser Datenbank verbinden.
REVOKE CONNECT ON DATABASE skytech FROM PUBLIC;
GRANT CONNECT ON DATABASE skytech TO skytech_app, skytech_collector, skytech_admin, skytech_reader, skytech_grafana;
-- skytech_admin darf eigene Schemas anlegen.
GRANT CREATE ON DATABASE skytech TO skytech_admin;
