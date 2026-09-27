/* Antworttypen der Add-on-API. Spiegeln exakt, was app/main.py liefert —
   siehe docs/api-referenz.md. */

export interface ServiceHealth {
  key: string
  label: string
  is_ok: boolean
  detail: string
}

export interface StatusResponse {
  version: string
  services: ServiceHealth[]
  /** Menschenlesbar, TT.MM.JJJJ hh:mm:ss in Berliner Zeit. */
  checked_at: string
  checked_at_iso: string
}
