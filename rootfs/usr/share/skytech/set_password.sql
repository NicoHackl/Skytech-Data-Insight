-- Setzt das Passwort einer Anmelderolle zur Laufzeit (Seite „Zugänge", D-025).
-- Rolle und Passwort kommen über die Umgebung von psql, nie über die
-- Kommandozeile. Leeres Passwort sperrt die Anmeldung über das Netz.
-- Welche Rollen erlaubt sind, prüft der Verwaltungsdienst (access_service.py).
\set ON_ERROR_STOP on
\getenv role SKYTECH_ROLE
\getenv password SKYTECH_PASSWORD

SELECT CASE WHEN :'password' = ''
            THEN format('ALTER ROLE %I PASSWORD NULL', :'role')
            ELSE format('ALTER ROLE %I PASSWORD %L', :'role', :'password') END
\gexec
