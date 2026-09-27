-- Grundobjekte der Datenbank. Läuft bei jedem Start (init-postgres) und muss
-- deshalb idempotent sein. Fachliche Tabellen entstehen nicht hier, sondern
-- über den Migrationsrunner (M1).

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'skytech_app') THEN
        CREATE ROLE skytech_app LOGIN;
    END IF;
END
$$;

SELECT 'CREATE DATABASE skytech OWNER skytech_app ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'skytech')
\gexec
