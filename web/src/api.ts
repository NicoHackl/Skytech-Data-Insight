import type { StatusResponse } from './types'

/* Einziger Ort im Frontend, an dem fetch aufgerufen wird. Basis-Pfad, Header und
   Fehlerbehandlung liegen damit an genau einer Stelle.

   Die Pfade sind relativ und beginnen bewusst OHNE Schrägstrich: Unter dem
   HA-Ingress läuft die Oberfläche unter /api/hassio_ingress/<token>/, und
   „/api/status" würde bei Home Assistant selbst landen statt beim Add-on
   (D-008, siehe docs/frontend.md). */

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message)
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`api${path}`, options)
  const isJson = response.headers.get('content-type')?.includes('application/json')
  const body: unknown = isJson ? await response.json() : await response.text()

  if (!response.ok) {
    // Das Add-on meldet Fehler als {"error": "…"}; Fremdschichten (Ingress, nginx) als Text.
    const errorText = isJson && typeof body === 'object' && body !== null
      ? (body as Record<string, unknown>).error
      : body
    const message = typeof errorText === 'string' && errorText
      ? errorText
      : `Anfrage fehlgeschlagen (${response.status}).`
    throw new ApiError(message, response.status)
  }
  return body as T
}

/* Jeder Aufruf ist ein benannter Eintrag — kein roher Pfad in einer Seite. */
export const api = {
  status: () => request<StatusResponse>('/status'),
}

/** Relativer Verweis auf Grafana im selben Ingress (D-006). */
export const GRAFANA_PATH = 'grafana/'
