import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, GRAFANA_PATH } from '../api'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { fmtBytes, fmtCount } from '../format'
import type { ServiceHealth, StatusResponse } from '../types'

/* Startseite: Zustand der Dienste, Kennzahlen der Aufzeichnung, Zugänge.
   Alle 10 s neu abgefragt. */

const POLL_MS = 10000
const BUFFER_WARN = 1000

const SERVICE_ICONS: Record<string, string> = {
  database: 'database',
  grafana: 'chart',
  collector: 'pulse',
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
  const recording = data?.aufzeichnung
  // Im LAN ist das Add-on unter derselben Adresse erreichbar wie Home Assistant.
  const host = window.location.hostname

  return (
    <>
      <PageHeader
        title="Übersicht"
        subtitle="Dienste und Aufzeichnung"
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
                  <h2>Aufzeichnung</h2>
                  <div className="sub">Rohwerte bei jeder Änderung, Minutenwerte zeitgewichtet</div>
                </div>
                <div className="spacer" />
                <Link className="btn btn-ghost btn-sm" to="/sensoren"><Icon name="pulse" size={16} />Sensoren</Link>
              </div>
              <div className="card-body">
                {recording ? (
                  <>
                    <div className="kv-row"><span className="k">Aktive Sensoren</span><span className="v">{fmtCount(recording.sensoren_aktiv)}</span></div>
                    <div className="kv-row"><span className="k">Werte in der letzten Minute</span><span className="v">{fmtCount(recording.werte_letzte_minute)}</span></div>
                    <div className="kv-row"><span className="k">Zuletzt geschrieben</span><span className="v">{recording.letzte_schreibung ?? '–'}</span></div>
                    <div className="kv-row"><span className="k">Minutenwerte berechnet bis</span><span className="v">{recording.minutenwerte_bis ?? '–'}</span></div>
                    {/* Der Puffer wird alle 2 s geleert; erst ein Stau deutet auf eine gestörte Datenbank. */}
                    <div className="kv-row">
                      <span className="k">Im Schreibpuffer</span>
                      <span className={`v ${recording.puffer > BUFFER_WARN ? 'warn' : 'muted'}`}>{fmtCount(recording.puffer)} Werte</span>
                    </div>
                    {recording.verworfen > 0 ? (
                      <div className="kv-row"><span className="k">Verworfen (Puffer voll)</span><span className="v err">{fmtCount(recording.verworfen)}</span></div>
                    ) : null}
                  </>
                ) : <div className="muted">Die Aufzeichnung startet noch.</div>}
                <div className="kv-row"><span className="k">Größe der Datenbank</span><span className="v">{fmtBytes(data.datenbank_bytes)}</span></div>
              </div>
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
                  Grafana-Benutzer „admin" und dem Passwort von der Seite „Zugänge".
                </div>
              </div>
            </div>

            <div className="card section-card">
              <div className="card-head">
                <div>
                  <h2>Datenbankzugang</h2>
                  <div className="sub">Für VSCode (z. B. Erweiterung „PostgreSQL") oder andere SQL-Werkzeuge</div>
                </div>
              </div>
              <div className="card-body">
                <div className="kv-row"><span className="k">Server</span><span className="v mono">{host}</span></div>
                <div className="kv-row"><span className="k">Port</span><span className="v mono">5432</span></div>
                <div className="kv-row"><span className="k">Datenbank</span><span className="v mono">skytech</span></div>
                <div className="kv-row"><span className="k">Vollzugriff</span><span className="v mono">skytech_admin</span></div>
                <div className="kv-row"><span className="k">Nur lesen</span><span className="v mono">skytech_reader</span></div>
                <div className="kv-row"><span className="k">Verschlüsselung</span><span className="v">aus (sslmode=disable)</span></div>
                <div className="hint-box">
                  Passwörter auf der Seite <Link to="/zugaenge">Zugänge</Link> neu erzeugen oder sperren; ohne Passwort
                  ist die Anmeldung gesperrt. Port 5432 nie ins Internet freigeben.
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
