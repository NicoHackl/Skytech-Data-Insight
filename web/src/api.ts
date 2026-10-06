import type {
  BackupFile, BackupsResponse, Catalog, HaEntity, LogResponse, LogSource, MigrationSql, MigrationsResponse, Retention,
  Sensor, SensorDraft, SensorFieldsValue, StatusResponse, StorageResponse, UploadResult,
} from './types'

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
  if (options.body && !(options.body instanceof Blob)) headers.set('Content-Type', 'application/json')
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

  /* Speicher und Aufbewahrung (M3). */
  storage: () => request<StorageResponse>('/storage'),
  retention: () => request<Retention>('/retention'),
  updateRetention: (retention: Retention) =>
    request<Retention & { sicherung: string }>('/retention', { method: 'PUT', body: JSON.stringify(retention) }),

  /* Protokoll (M3): neueste zuerst, ältere über die id des letzten Eintrags. */
  log: (source: LogSource | '', beforeId?: number) => {
    const query = new URLSearchParams({ limit: '50' })
    if (source) query.set('quelle', source)
    if (beforeId !== undefined) query.set('vor', String(beforeId))
    return request<LogResponse>(`/log?${query.toString()}`)
  },

  /* Migrationen (M3, nur lesend). */
  migrations: () => request<MigrationsResponse>('/migrations'),
  migrationSql: (version: number) => request<MigrationSql>(`/migrations/${version}`),

  /* Sicherungen (M2). Downloads laufen als normale Links (BACKUP_*_PATH),
     damit der Browser große Dateien selbst speichert. */
  backups: () => request<BackupsResponse>('/backups'),
  createBackup: () => request<BackupFile>('/backups', { method: 'POST' }),
  deleteBackup: (name: string) => request<{ ok: boolean }>(`/backups/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  uploadBackup: (file: File) =>
    request<UploadResult>(`/backups/upload?name=${encodeURIComponent(file.name)}`, {
      method: 'PUT',
      body: file,
      headers: { 'Content-Type': 'application/octet-stream' },
    }),
  restoreBackup: (name: string) =>
    request<{ ok: boolean }>(`/backups/${encodeURIComponent(name)}/restore`, {
      method: 'POST',
      body: JSON.stringify({ bestaetigung: 'WIEDERHERSTELLEN' }),
    }),
}

/** Download des Komplettpakets (Datenbank + Grafana). */
export const BACKUP_ARCHIVE_PATH = 'api/backups/download'
/** Download einer einzelnen Sicherung. */
export const backupFilePath = (name: string) => `api/backups/${encodeURIComponent(name)}`

/** Relativer Verweis auf Grafana im selben Ingress (D-006). */
export const GRAFANA_PATH = 'grafana/'
