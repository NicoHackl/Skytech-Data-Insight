-- 0002 Größe „Preis" für Tarif- und Börsenpreise (z. B. €/kWh).
-- ON CONFLICT: Anlagen, die den Eintrag schon per INSERT angelegt haben (D-018),
-- laufen ohne Fehler durch.

INSERT INTO skytech.groesse (schluessel, bezeichnung, reihenfolge) VALUES
    ('preis', 'Preis', 80)
ON CONFLICT (schluessel) DO NOTHING;
