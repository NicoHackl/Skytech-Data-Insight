import { useCallback, useEffect, useState } from 'react'
import { api, GRAFANA_PATH } from '../api'
import { PageHeader } from '../components/Layout'
import { Icon } from '../components/Icon'
import type { ServiceHealth, StatusResponse } from '../types'

/* Startseite: Zustand der Dienste im Add-on und der Weg zu Grafana.
   Alle 10 s neu abgefragt — die Werte ändern sich nur bei Start, Absturz
   oder Update eines Dienstes. */

const POLL_MS = 10000

const SERVICE_ICONS: Record<string, string> = {
  database: 'database',
  grafana: 'chart',
}

function ServiceTile({ service }: { service: ServiceHealth }) {
  return (
    <div className="tile static">
      <div className="tile-icon"><Icon name={SERVICE_ICONS[service.key] ?? 'info'} /></div>
      <h3>{service.label}</h3>
      <div className={`num ${service.is_ok ? 'ok' : 'warn'}`}>{service.is_ok ? 'Läuft' : 'Gestört'}</div>
      <p>{service.detail}</p>
    </div>
  )
}

export function Uebersicht() {
  const [data, setData] = useState<StatusResponse | null>(null)
  const [connectionError, setConnectionError] = useState('')

  const load = useCallback(async () => {
    try {
      setData(await api.status())
      setConnectionError('')
    } catch (error) {
      setConnectionError((error as Error).message)
    }
  }, [])

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(), POLL_MS)
    return () => window.clearInterval(timer)
  }, [load])

  const allOk = data?.services.every((service) => service.is_ok) ?? false

  return (
    <>
      <PageHeader
        title="Übersicht"
        subtitle="Dienste des Add-ons"
        actions={data
          ? <span className={`pill ${allOk ? 'ok' : 'warn'}`}>{allOk ? 'Alle Dienste laufen' : 'Dienst gestört'}</span>
          : null}
      />
      <div className="content">
        {connectionError ? <div className="alert">Verbindungsfehler: {connectionError}</div> : null}

        {!data && !connectionError ? <div className="center"><div className="spinner" /></div> : null}

        {data ? (
          <>
            <div className="tiles">
              {data.services.map((service) => <ServiceTile key={service.key} service={service} />)}
            </div>

            <div className="card section-card">
              <div className="card-head">
                <div>
                  <h2>Grafana</h2>
                  <div className="sub">Dashboards für Leistung, Energie und Soll/Ist-Werte</div>
                </div>
                <div className="spacer" />
                <a className="btn btn-ghost btn-sm" href={GRAFANA_PATH} target="_blank" rel="noreferrer">
                  <Icon name="external" size={16} />Neuer Tab
                </a>
                <a className="btn btn-primary btn-sm" href={GRAFANA_PATH}>
                  <Icon name="chart" size={16} />Grafana öffnen
                </a>
              </div>
              <div className="card-body">
                <div className="hint-box">
                  Über das Home-Assistant-Seitenmenü sind Sie in Grafana automatisch angemeldet.
                  Im LAN ist Grafana zusätzlich unter Port 3000 erreichbar – dort mit dem
                  Grafana-Benutzer „admin" und dem Passwort aus der Add-on-Konfiguration.
                </div>
              </div>
            </div>

            <div className="meta-line">Version {data.version} · geprüft {data.checked_at}</div>
          </>
        ) : null}
      </div>
    </>
  )
}
