import { Fragment, useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { useToast } from '../components/Toast'
import type { MigrationStatus, MigrationsResponse } from '../types'

/* Migrationen (M3): Stand der Schemaänderungen, nur lesend. Angelegt werden
   Migrationen über das MCP-Werkzeug „migration_anlegen“ oder als Datei. */

const STATUS: Record<MigrationStatus, { label: string; pill: string }> = {
  angewendet: { label: 'Angewendet', pill: 'ok' },
  ausstehend: { label: 'Ausstehend', pill: 'warn' },
  geaendert: { label: 'Datei geändert', pill: 'err' },
  datei_fehlt: { label: 'Datei fehlt', pill: 'muted' },
}

const number = (version: number) => String(version).padStart(4, '0')

export function Migrationen() {
  const [data, setData] = useState<MigrationsResponse | null>(null)
  const [loadError, setLoadError] = useState('')
  const [sql, setSql] = useState<Record<number, string>>({})
  const [open, setOpen] = useState<number | null>(null)
  const { toast } = useToast()

  const load = useCallback(async () => {
    try {
      setData(await api.migrations())
      setLoadError('')
    } catch (error) {
      setLoadError((error as Error).message)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const toggle = async (version: number) => {
    if (open === version) {
      setOpen(null)
      return
    }
    if (!(version in sql)) {
      try {
        const response = await api.migrationSql(version)
        setSql((current) => ({ ...current, [version]: response.sql }))
      } catch (error) {
        toast((error as Error).message, 'err')
        return
      }
    }
    setOpen(version)
  }

  // „Datei fehlt“ ist nur ein Hinweis: die Änderung steckt in der Datenbank.
  const count = (status: MigrationStatus) => data?.migrationen.filter((item) => item.status === status).length ?? 0
  const changed = count('geaendert')
  const pending = count('ausstehend')
  const headerPill = changed
    ? <span className="pill err">{changed} geändert</span>
    : <span className={`pill ${pending ? 'warn' : 'ok'}`}>{pending ? `${pending} ausstehend` : 'Alles angewendet'}</span>

  return (
    <>
      <PageHeader
        title="Migrationen"
        subtitle="Schemaänderungen der Datenbank"
        actions={data ? headerPill : null}
      />
      <div className="content">
        {loadError ? <div className="alert">{loadError}</div> : null}
        {data?.fehler ? <div className="alert"><Icon name="warning" size={16} />{data.fehler}</div> : null}
        <div className="info-strip">
          <Icon name="info" size={16} />
          System-Migrationen kommen mit dem Add-on. Eigene liegen in /data/migrations (Nummern ab 1000), angelegt
          über das MCP-Werkzeug „migration_anlegen“ oder von Hand; sie laufen beim nächsten Start.
        </div>
        <div className="card section-card">
          {!data && !loadError ? <div className="center"><div className="spinner" /></div> : null}
          {data && data.migrationen.length === 0 ? (
            <div className="empty"><Icon name="layers" size={40} /><p>Keine Migrationen gefunden.</p></div>
          ) : null}
          {data && data.migrationen.length > 0 ? (
            <div className="table-wrap">
              <table className="data static-rows">
                <thead>
                  <tr><th>Migration</th><th>Quelle</th><th>Status</th><th>Angewendet</th><th /></tr>
                </thead>
                <tbody>
                  {data.migrationen.map((item) => (
                    <Fragment key={item.version}>
                      <tr>
                        <td><span className="cell-title">{item.name.replaceAll('_', ' ')}</span><span className="cell-sub mono">{number(item.version)}_{item.name}.sql</span></td>
                        <td>{item.quelle === 'system' ? 'System' : 'Anlage'}</td>
                        <td><span className={`pill ${STATUS[item.status].pill}`}>{STATUS[item.status].label}</span></td>
                        <td>{item.angewendet_am ?? '–'}</td>
                        <td>
                          <div className="row-actions">
                            <button type="button" className="btn btn-ghost btn-sm" disabled={item.status === 'datei_fehlt'}
                              aria-expanded={open === item.version} onClick={() => void toggle(item.version)}>
                              <Icon name={open === item.version ? 'up' : 'down'} size={16} />SQL
                            </button>
                          </div>
                        </td>
                      </tr>
                      {open === item.version ? (
                        <tr><td colSpan={5}><pre className="code-block">{sql[item.version]}</pre></td></tr>
                      ) : null}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      </div>
    </>
  )
}
