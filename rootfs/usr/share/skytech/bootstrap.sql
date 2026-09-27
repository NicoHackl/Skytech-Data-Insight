-- Grundobjekte der Datenbank: Rollen und Datenbank. Läuft bei jedem Start
-- (init-postgres) als Superuser und muss deshalb idempotent sein. Fachliche
-- Tabellen entstehen nicht hier, sondern über den Migrationsrunner des
-- Verwaltungsdienstes (app/sql/).
--
-- Rollen (docs/datenmodell.md):
--   skytech_app        Besitzer aller Objekte, führt Migrationen aus (Socket)
--   skytech_collector  schreibt Messwerte (Socket)
--   skytech_admin      Vollzugriff aus dem LAN, z. B. VSCode (Passwort)
--   skytech_reader     nur lesen aus dem LAN (Passwort)
--   skytech_grafana    Datenquelle von Grafana, liest wie skytech_reader (lokal, erzeugtes Passwort)

DO $$
DECLARE
    rolle text;
BEGIN
    FOREACH rolle IN ARRAY ARRAY['skytech_app', 'skytech_collector', 'skytech_admin', 'skytech_reader', 'skytech_grafana'] LOOP
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = rolle) THEN
            EXECUTE format('CREATE ROLE %I LOGIN', rolle);
        END IF;
    END LOOP;
END
$$;

-- skytech_admin handelt mit den Rechten des Besitzers (DDL, Migrationen von Hand, MCP).
GRANT skytech_app TO skytech_admin;
-- Grafana liest genau das, was skytech_reader lesen darf.
GRANT skytech_reader TO skytech_grafana;

SELECT 'CREATE DATABASE skytech OWNER skytech_app ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'skytech')
\gexec

-- Passwörter für den LAN-Zugang kommen aus den Add-on-Optionen und werden
-- über die Umgebung von psql übergeben, nie über die Kommandozeile. Ein leeres
-- Passwort sperrt die Anmeldung über das Netz.
\getenv admin_password SKYTECH_DB_ADMIN_PASSWORD
\getenv reader_password SKYTECH_DB_READER_PASSWORD
\getenv grafana_password SKYTECH_DB_GRAFANA_PASSWORD

SELECT CASE WHEN :'admin_password' = ''
            THEN 'ALTER ROLE skytech_admin PASSWORD NULL'
            ELSE format('ALTER ROLE skytech_admin PASSWORD %L', :'admin_password') END
\gexec
SELECT CASE WHEN :'reader_password' = ''
            THEN 'ALTER ROLE skytech_reader PASSWORD NULL'
            ELSE format('ALTER ROLE skytech_reader PASSWORD %L', :'reader_password') END
\gexec
SELECT format('ALTER ROLE skytech_grafana PASSWORD %L', :'grafana_password')
\gexec
