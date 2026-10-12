import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { useToast } from '../components/Toast'
import { fmtValue } from '../format'
import type { Catalog, Sensor } from '../types'

/* Liste der aufgezeichneten Sensoren. Klick auf eine Zeile öffnet die
   Bearbeitung; der Schalter pausiert die Aufzeichnung direkt in der Liste.
   Sensoren, die Skytech HEMS über seinen Vertrag verwaltet (D-027), stehen in
   einem eigenen Abschnitt und lassen sich hier nicht ändern. */

const POLL_MS = 15000

export function Sensoren() {
  const [sensors, setSensors] = useState<Sensor[] | null>(null)
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [filter, setFilter] = useState('')
  const [category, setCategory] = useState('')
  const [busy, setBusy] = useState<number | null>(null)
  const [loadError, setLoadError] = useState('')
  const { toast } = useToast()
  const navigate = useNavigate()

  const load = useCallback(async () => {
    try {
      const [list, cat] = await Promise.all([api.sensors(), api.catalog()])
      setSensors(list)
      setCatalog(cat)
      setLoadError('')
    } catch (error) {
      setLoadError((error as Error).message)
    }
  }, [])

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(), POLL_MS)
    return () => window.clearInterval(timer)
  }, [load])

  const label = useCallback(
    (list: Catalog['kategorien'] | undefined, key: string) => list?.find((entry) => entry.schluessel === key)?.bezeichnung ?? key,
    [],
  )

  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase()
    return (sensors ?? []).filter((sensor) =>
      (!category || sensor.kategorie === category)
      && (!needle || [sensor.name, sensor.entity_id, sensor.attribut, sensor.anlage].some((text) => text?.toLowerCase().includes(needle))))
  }, [sensors, filter, category])

  const toggleActive = async (sensor: Sensor) => {
    setBusy(sensor.id)
    try {
      await api.updateSensor(sensor.id, { aktiv: !sensor.aktiv })
      toast(sensor.aktiv ? `„${sensor.name}“ pausiert.` : `„${sensor.name}“ wird wieder aufgezeichnet.`)
      await load()
    } catch (error) {
      toast((error as Error).message, 'err')
    } finally {
      setBusy(null)
    }
  }

  const activeCount = sensors?.filter((sensor) => sensor.aktiv).length ?? 0
  const managed = visible.filter((sensor) => sensor.verwaltet_von)
  const own = visible.filter((sensor) => !sensor.verwaltet_von)

  const cells = (sensor: Sensor) => (
    <>
      <td>
        <span className="cell-title">{sensor.name}</span>
        <span className="cell-sub mono">{sensor.entity_id}{sensor.attribut ? ` → ${sensor.attribut}` : ''}</span>
      </td>
      <td>{label(catalog?.kategorien, sensor.kategorie)}</td>
      <td>
        {label(catalog?.groessen, sensor.groesse)}
        {sensor.energie_zaehler ? <span className="cell-sub">Zählerstand</span> : null}
      </td>
      <td>
        {sensor.anlage ?? <span className="muted">–</span>}
        {sensor.soll_ist_paar ? <span className="cell-sub">{sensor.rolle === 'soll' ? 'Soll' : 'Ist'} · {sensor.soll_ist_paar}</span> : null}
      </td>
      <td>
        {fmtValue(sensor.letzter_wert, sensor.letzter_text, sensor.einheit)}
        <span className="cell-sub">{sensor.letzte_zeit_text ?? 'noch kein Wert'}</span>
      </td>
    </>
  )

  return (
    <>
      <PageHeader
        title="Sensoren"
        subtitle={sensors ? `${activeCount} von ${sensors.length} werden aufgezeichnet` : 'Aufgezeichnete Werte aus Home Assistant'}
        actions={<Link className="btn btn-primary" to="/sensoren/neu"><Icon name="plus" size={16} />Sensoren hinzufügen</Link>}
      />
      <div className="content">
        {loadError ? <div className="alert">{loadError}</div> : null}
        {!sensors && !loadError ? <div className="center"><div className="spinner" /></div> : null}

        {sensors && sensors.length === 0 ? (
          <div className="card">
            <div className="empty">
              <Icon name="pulse" size={36} />
              <p>Noch keine Sensoren. Wählen Sie Entitäten aus Home Assistant, die aufgezeichnet werden sollen.</p>
              <Link className="btn btn-primary" to="/sensoren/neu"><Icon name="plus" size={16} />Ersten Sensor hinzufügen</Link>
            </div>
          </div>
        ) : null}

        {sensors && sensors.length > 0 ? (
          <>
            <div className="card">
              <div className="card-head filter-bar">
                <input type="search" placeholder="Suchen: Name, Entität, Anlage …" value={filter} onChange={(event) => setFilter(event.target.value)} aria-label="Sensoren durchsuchen" />
                <select value={category} onChange={(event) => setCategory(event.target.value)} aria-label="Nach Kategorie filtern">
                  <option value="">Alle Kategorien</option>
                  {catalog?.kategorien.map((entry) => <option key={entry.schluessel} value={entry.schluessel}>{entry.bezeichnung}</option>)}
                </select>
              </div>
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Kategorie</th>
                      <th>Größe</th>
                      <th>Anlage / Paar</th>
                      <th>Letzter Wert</th>
                      <th>Aufzeichnung</th>
                    </tr>
                  </thead>
                  <tbody>
                    {own.map((sensor) => (
                      <tr key={sensor.id} onClick={() => navigate(`/sensoren/${sensor.id}`)}>
                        {cells(sensor)}
                        <td onClick={(event) => event.stopPropagation()}>
                          <label className="switch table-switch">
                            <input
                              type="checkbox"
                              checked={sensor.aktiv}
                              disabled={busy === sensor.id}
                              onChange={() => void toggleActive(sensor)}
                              aria-label={`Aufzeichnung von ${sensor.name} ${sensor.aktiv ? 'pausieren' : 'fortsetzen'}`}
                            />
                            <span className="track" />
                          </label>
                        </td>
                      </tr>
                    ))}
                    {own.length === 0 ? (
                      <tr><td colSpan={6} className="muted">
                        {sensors.some((sensor) => !sensor.verwaltet_von) ? 'Kein eigener Sensor passt zum Filter.' : 'Noch keine eigenen Sensoren.'}
                      </td></tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </div>

            {managed.length ? (
              <>
                <div className="section-title"><Icon name="key" size={14} />Über Vertrag verwaltet — Skytech HEMS</div>
                <div className="card">
                  <div className="card-body">
                    <div className="hint-box">
                      Diese Sensoren hat Skytech HEMS angelegt oder übernommen. Sie sind hier gesperrt und lassen sich nur im
                      HEMS-Tab „Dynamischer Strompreis“ ändern oder austauschen.
                    </div>
                  </div>
                  <div className="table-wrap">
                    <table className="data">
                      <thead>
                        <tr>
                          <th>Name</th>
                          <th>Kategorie</th>
                          <th>Größe</th>
                          <th>Anlage / Paar</th>
                          <th>Letzter Wert</th>
                          <th>HEMS-Rolle</th>
                        </tr>
                      </thead>
                      <tbody>
                        {managed.map((sensor) => (
                          <tr key={sensor.id} onClick={() => navigate(`/sensoren/${sensor.id}`)}>
                            {cells(sensor)}
                            <td>
                              <span className={`pill ${sensor.aktiv ? 'ok' : 'muted'}`}>{sensor.aktiv ? 'Aktiv' : 'Stillgelegt'}</span>
                              <span className="cell-sub mono">{sensor.hems_rollen.length ? sensor.hems_rollen.join(', ') : 'keine Rolle'}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            ) : null}
          </>
        ) : null}
      </div>
    </>
  )
}
