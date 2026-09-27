import type { Catalog, HaEntity, Sensor, SensorDraft, SensorFieldsValue, StatusResponse } from './types'

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
    /** Feldfehler des Servers (422), Schlüssel wie im Formular. */
    public fieldErrors: Record<string, string> = {},
  ) {
    super(message)
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body) headers.set('Content-Type', 'application/json')
  const response = await fetch(`api${path}`, { ...options, headers })
  const isJson = response.headers.get('content-type')?.includes('application/json')
  const body: unknown = isJson ? await response.json() : await response.text()

  if (!response.ok) {
    // Das Add-on meldet Fehler als {"error": "…", "field_errors": {…}}; Fremdschichten als Text.
    const errorBody = isJson && typeof body === 'object' && body !== null ? body as Record<string, unknown> : undefined
    const errorText = errorBody?.error ?? body
    const message = response.status === 401
      ? 'Sitzung abgelaufen – bitte die Seite neu laden.'
      : typeof errorText === 'string' && errorText ? errorText : `Anfrage fehlgeschlagen (${response.status}).`
    const fieldErrors = (errorBody?.field_errors ?? {}) as Record<string, string>
    throw new ApiError(message, response.status, fieldErrors)
  }
  return body as T
}

/* Jeder Aufruf ist ein benannter Eintrag — kein roher Pfad in einer Seite. */
export const api = {
  status: () => request<StatusResponse>('/status'),
  catalog: () => request<Catalog>('/catalog'),
  sensors: () => request<{ sensors: Sensor[] }>('/sensors').then((body) => body.sensors),
  createSensors: (sensors: SensorDraft[]) =>
    request<{ ids: number[] }>('/sensors', { method: 'POST', body: JSON.stringify({ sensors }) }),
  updateSensor: (id: number, changes: Partial<SensorFieldsValue>) =>
    request<{ ok: boolean }>(`/sensors/${id}`, { method: 'PUT', body: JSON.stringify(changes) }),
  deleteSensor: (id: number) => request<{ ok: boolean }>(`/sensors/${id}`, { method: 'DELETE' }),
  haEntities: () => request<{ entities: HaEntity[] }>('/ha/entities').then((body) => body.entities),
}

/** Relativer Verweis auf Grafana im selben Ingress (D-006). */
export const GRAFANA_PATH = 'grafana/'
