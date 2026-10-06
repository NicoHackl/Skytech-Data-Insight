import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { useToast } from '../components/Toast'
import type { LogEntry, LogSource } from '../types'

/* Protokoll (M3): jede Änderung aus Oberfläche, MCP und System, neueste zuerst.
   Ältere Einträge werden seitenweise nachgeladen. */

const SOURCES: Record<LogSource, { label: string; pill: string }> = {
  ui: { label: 'Oberfläche', pill: 'primary' },
  mcp: { label: 'MCP', pill: 'warn' },
  system: { label: 'System', pill: 'muted' },
}

const ACTIONS: Record<string, string> = {
  sensoren_angelegt: 'Sensoren angelegt',
  sensor_geaendert: 'Sensor geändert',
  sensor_geloescht: 'Sensor gelöscht',
  aufbewahrung_geaendert: 'Aufbewahrung geändert',
  sicherung_erstellt: 'Sicherung angelegt',
  sicherung_geloescht: 'Sicherung gelöscht',
  sicherung_heruntergeladen: 'Komplettsicherung heruntergeladen',
  sicherung_wiederhergestellt: 'Sicherung eingespielt',
  sql_ausgefuehrt: 'SQL ausgeführt',
  migration_angewendet: 'Migration angewendet',
  dashboard_gespeichert: 'Dashboard gespeichert',
  dashboard_geloescht: 'Dashboard gelöscht',
  zugang_neu: 'Zugangsdaten neu erzeugt',
  zugang_gesperrt: 'Zugang gesperrt',
}

export function Protokoll() {
  const [entries, setEntries] = useState<LogEntry[] | null>(null)
  const [more, setMore] = useState(false)
  const [source, setSource] = useState<LogSource | ''>('')
  const [loadError, setLoadError] = useState('')
  const [loadingMore, setLoadingMore] = useState(false)
  const { toast } = useToast()

  const load = useCallback(async () => {
    setEntries(null)
    try {
      const response = await api.log(source)
      setEntries(response.eintraege)
      setMore(response.weitere)
      setLoadError('')
    } catch (error) {
      setLoadError((error as Error).message)
    }
  }, [source])

  useEffect(() => { void load() }, [load])

  const loadOlder = async () => {
    if (!entries?.length) return
    setLoadingMore(true)
    try {
      const response = await api.log(source, entries[entries.length - 1].id)
      setEntries([...entries, ...response.eintraege])
      setMore(response.weitere)
    } catch (error) {
      toast((error as Error).message, 'err')
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <>
      <PageHeader title="Protokoll" subtitle="Änderungen aus Oberfläche, MCP und System" />
      <div className="content">
        {loadError ? <div className="alert">{loadError}</div> : null}
        <div className="card">
          <div className="card-head filter-bar">
            <select value={source} onChange={(event) => setSource(event.target.value as LogSource | '')} aria-label="Nach Quelle filtern">
              <option value="">Alle Quellen</option>
              {(Object.keys(SOURCES) as LogSource[]).map((key) => <option key={key} value={key}>{SOURCES[key].label}</option>)}
            </select>
            <div className="spacer" />
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => void load()}><Icon name="refresh" size={16} />Aktualisieren</button>
          </div>
          {!entries && !loadError ? <div className="center"><div className="spinner" /></div> : null}
          {entries && entries.length === 0 ? (
            <div className="empty">
              <Icon name="list" size={40} />
              <p>Noch keine Einträge{source ? ` aus „${SOURCES[source].label}“` : ''}. Jede Änderung an Sensoren, Aufbewahrung, Sicherungen oder per MCP erscheint hier.</p>
            </div>
          ) : null}
          {entries && entries.length > 0 ? (
            <div className="table-wrap">
              <table className="data static-rows">
                <thead>
                  <tr><th>Zeit</th><th>Quelle</th><th>Aktion</th></tr>
                </thead>
                <tbody>
                  {entries.map((entry) => (
                    <tr key={entry.id}>
                      <td><span className="cell-title">{entry.zeit_text}</span><span className="cell-sub">{entry.benutzer ?? '–'}</span></td>
                      <td><span className={`pill ${SOURCES[entry.quelle]?.pill ?? 'muted'}`}>{SOURCES[entry.quelle]?.label ?? entry.quelle}</span></td>
                      <td>
                        <span className="cell-title">{ACTIONS[entry.aktion] ?? entry.aktion}</span>
                        {Object.keys(entry.details).length > 0 ? (
                          <details className="code-details">
                            <summary>Details</summary>
                            <pre className="code-block">{JSON.stringify(entry.details, null, 2)}</pre>
                          </details>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
        {more ? (
          <div className="inline-actions card-actions">
            <button type="button" className="btn btn-ghost" disabled={loadingMore} onClick={() => void loadOlder()}>
              <Icon name="down" size={16} />{loadingMore ? 'Lädt …' : 'Ältere Einträge laden'}
            </button>
          </div>
        ) : null}
      </div>
    </>
  )
}
