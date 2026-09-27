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
