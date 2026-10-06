import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { RetentionCard } from '../components/RetentionCard'
import { fmtBytes, fmtCount } from '../format'
import type { StorageResponse } from '../types'

/* Speicher (M3): Belegung je Tabelle, Wachstum der Rohwerte, Aufbewahrung. */

const TABLE_LABELS: Record<string, string> = {
  messwert: 'Rohwerte',
  messwert_1min: 'Minutenwerte',
  messwert_15min: 'Verdichtung 15 Minuten',
  messwert_1h: 'Verdichtung Stunde',
  messwert_1d: 'Verdichtung Tag',
}

export function Speicher() {
  const [data, setData] = useState<StorageResponse | null>(null)
  const [loadError, setLoadError] = useState('')

  const load = useCallback(async () => {
    try {
      setData(await api.storage())
      setLoadError('')
    } catch (error) {
      setLoadError((error as Error).message)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const today = data?.rohwerte_je_tag.find((day) => day.heute)

  return (
    <>
      <PageHeader
        title="Speicher"
        subtitle="Belegung, Wachstum und Aufbewahrung"
        actions={<button type="button" className="btn btn-ghost" onClick={() => void load()}><Icon name="refresh" size={16} />Aktualisieren</button>}
      />
      <div className="content">
        {loadError ? <div className="alert">{loadError}</div> : null}
        {!data && !loadError ? <div className="center"><div className="spinner" /></div> : null}

        {data ? (
          <>
            <div className="tiles">
              <div className="tile static">
                <div className="tile-icon"><Icon name="database" /></div>
                <h3>Datenbank</h3>
                <div className="num">{fmtBytes(data.datenbank_bytes)}</div>
                <p>Gesamte Größe auf dem Datenträger</p>
              </div>
              <div className="tile static">
                <div className="tile-icon"><Icon name="pulse" /></div>
                <h3>Rohwerte je Tag</h3>
                <div className="num">{fmtCount(data.rohwerte_tag_mittel)}</div>
                <p>Mittel der letzten vollständigen Tage{today ? `, heute bisher ${fmtCount(today.rohwerte)}` : ''}</p>
              </div>
              <div className="tile static">
                <div className="tile-icon"><Icon name="chart" /></div>
                <h3>Rohwerte pro Jahr</h3>
                <div className="num">≈ {fmtBytes(data.rohwerte_bytes_jahr)}</div>
                <p>Hochrechnung unkomprimiert; nach 7 Tagen wird komprimiert</p>
              </div>
            </div>

            <div className="card section-card">
              <div className="card-head">
                <div>
                  <h2>Tabellen</h2>
                  <div className="sub">Daten liegen in Abschnitten (Chunks); ältere Abschnitte werden komprimiert</div>
                </div>
              </div>
              <div className="table-wrap">
                <table className="data static-rows">
                  <thead>
                    <tr><th>Tabelle</th><th>Größe</th><th>Abschnitte</th><th>Komprimiert</th></tr>
                  </thead>
                  <tbody>
                    {data.tabellen.map((table) => (
                      <tr key={table.name}>
                        <td><span className="cell-title">{TABLE_LABELS[table.name] ?? table.name}</span><span className="cell-sub mono">skytech.{table.name}</span></td>
                        <td>{fmtBytes(table.bytes)}</td>
                        <td>{fmtCount(table.chunks)}</td>
                        <td>{table.chunks === 0 ? '–' : `${fmtCount(table.komprimiert)} von ${fmtCount(table.chunks)}`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {data.rohwerte_je_tag.length > 0 ? (
              <div className="card section-card">
                <div className="card-head">
                  <div>
                    <h2>Rohwerte der letzten Tage</h2>
                    <div className="sub">Anzahl gespeicherter Änderungen je Kalendertag</div>
                  </div>
                </div>
                <div className="card-body">
                  {data.rohwerte_je_tag.map((day) => (
                    <div className="kv-row" key={day.tag}>
                      <span className="k">{day.tag}{day.heute ? ' (heute)' : ''}</span>
                      <span className="v">{fmtCount(day.rohwerte)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </>
        ) : null}

        <RetentionCard onSaved={() => void load()} />
      </div>
    </>
  )
}
