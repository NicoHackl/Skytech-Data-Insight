/* Antworttypen der Add-on-API. Spiegeln exakt, was app/main.py liefert —
   siehe docs/api-referenz.md. */

export interface ServiceHealth {
  key: string
  label: string
  is_ok: boolean
  detail: string
}

export interface RecordingStatus {
  sensoren_aktiv: number
  werte_letzte_minute: number
  puffer: number
  verworfen: number
  letzte_schreibung: string | null
  minutenwerte_bis: string | null
}

export interface StatusResponse {
  version: string
  services: ServiceHealth[]
  aufzeichnung: RecordingStatus | null
  datenbank_bytes: number | null
  /** Menschenlesbar, TT.MM.JJJJ hh:mm:ss in Berliner Zeit. */
  checked_at: string
  checked_at_iso: string
}

export interface CatalogEntry {
  schluessel: string
  bezeichnung: string
}

export interface Catalog {
  kategorien: CatalogEntry[]
  groessen: CatalogEntry[]
  anlagen: string[]
  paare: string[]
}

export type Rolle = 'ist' | 'soll' | null

/** Bearbeitbare Felder eines Sensors — so, wie sie an die API gehen. */
export interface SensorFieldsValue {
  name: string
  kategorie: string
  groesse: string
  rolle: Rolle
  soll_ist_paar: string | null
  einheit: string | null
  anlage: string | null
  energie_zaehler: boolean
  aktiv: boolean
}

export interface SensorDraft extends SensorFieldsValue {
  entity_id: string
  attribut: string | null
}

export interface Sensor extends SensorDraft {
  id: number
  quelle: string
  erstellt_am: string
  letzte_zeit: string | null
  letzte_zeit_text: string | null
  letzter_wert: number | null
  letzter_text: string | null
}

export interface Suggestion {
  entity_id: string
  attribut: string | null
  name: string
  kategorie: string
  groesse: string
  einheit: string | null
  energie_zaehler: boolean
}

export interface HaAttribute {
  name: string
  wert: unknown
  erfasst: boolean
  vorschlag: Suggestion
}

export interface HaEntity {
  entity_id: string
  name: string
  domain: string
  state: string | null
  einheit: string | null
  device_class: string | null
  state_class: string | null
  erfasst: boolean
  vorschlag: Suggestion
  attribute: HaAttribute[]
}

export interface BackupFile {
  datei: string
  art: string
  art_text: string
  groesse_bytes: number
  erstellt: string
  erstellt_iso: string
}

export interface RestoreState {
  status: 'laeuft' | 'erfolgreich' | 'fehlgeschlagen' | 'unklar'
  datei: string
  benutzer: string | null
  gestartet: string
  beendet?: string
  meldung: string | null
  sicherung_vorher?: string
}

export interface BackupsResponse {
  sicherungen: BackupFile[]
  wiederherstellung: RestoreState | null
  laeuft: boolean
}

export interface UploadResult {
  datei: string
  original: string
  groesse_bytes: number
  grafana: boolean
  beschreibung: { version?: string; erstellt?: string } | null
}

/* Speicher und Aufbewahrung (M3) */

export interface StorageTable {
  name: string
  bytes: number
  chunks: number
  komprimiert: number
}

export interface StorageResponse {
  datenbank_bytes: number
  tabellen: StorageTable[]
  /** Rohwerte je Berliner Tag, `tag` als TT.MM.JJJJ. */
  rohwerte_je_tag: { tag: string; rohwerte: number; heute: boolean }[]
  rohwerte_tag_mittel: number
  /** Hochrechnung für ein Jahr Rohwerte, unkomprimiert. */
  rohwerte_bytes_jahr: number
}

/** Tage; `null` = nie löschen. */
export interface Retention {
  rohwerte_tage: number | null
  minutenwerte_tage: number | null
}
