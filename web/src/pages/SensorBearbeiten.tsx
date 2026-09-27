import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { SensorFields } from '../components/SensorFields'
import { useToast } from '../components/Toast'
import { fmtValue } from '../format'
import type { Catalog, Sensor, SensorFieldsValue } from '../types'

/* Einen Sensor bearbeiten oder löschen. Entität und Attribut sind fest – wer
   eine andere Quelle will, legt einen neuen Sensor an; die Messreihe bleibt so
   eindeutig einer Quelle zugeordnet. */

const FIELDS: (keyof SensorFieldsValue)[] = [
  'name', 'kategorie', 'groesse', 'rolle', 'soll_ist_paar', 'einheit', 'anlage', 'energie_zaehler', 'aktiv',
]

export function SensorBearbeiten() {
  const { id } = useParams()
  const sensorId = Number(id)
  const [sensor, setSensor] = useState<Sensor | null>(null)
  const [draft, setDraft] = useState<SensorFieldsValue | null>(null)
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [loadError, setLoadError] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const { toast } = useToast()
  const navigate = useNavigate()

  const load = useCallback(async () => {
    try {
      const [list, cat] = await Promise.all([api.sensors(), api.catalog()])
      const found = list.find((entry) => entry.id === sensorId)
      if (!found) {
        setLoadError('Sensor nicht gefunden – eventuell wurde er gelöscht.')
        return
      }
      setSensor(found)
      setDraft(Object.fromEntries(FIELDS.map((field) => [field, found[field]])) as unknown as SensorFieldsValue)
      setCatalog(cat)
    } catch (error) {
      setLoadError((error as Error).message)
    }
  }, [sensorId])

  useEffect(() => { void load() }, [load])

  const patch = (changes: Partial<SensorFieldsValue>) => {
    setDraft((current) => (current ? { ...current, ...changes } : current))
    setErrors((current) => {
      const remaining = { ...current }
      Object.keys(changes).forEach((field) => delete remaining[field])
      return remaining
    })
  }

  const changes = (): Partial<SensorFieldsValue> => {
    if (!sensor || !draft) return {}
    return Object.fromEntries(FIELDS.filter((field) => draft[field] !== sensor[field]).map((field) => [field, draft[field]]))
  }

  const save = async () => {
    const changed = changes()
    if (Object.keys(changed).length === 0) {
      navigate('/sensoren')
      return
    }
    setSaving(true)
    try {
      await api.updateSensor(sensorId, changed)
      toast('Gespeichert.')
      navigate('/sensoren')
    } catch (error) {
      const apiError = error as ApiError
      setErrors(apiError.fieldErrors ?? {})
      toast(apiError.message, 'err')
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    if (!sensor) return
    const confirmed = window.confirm(
      `„${sensor.name}“ wirklich löschen?\n\nAlle aufgezeichneten Werte dieses Sensors werden unwiderruflich gelöscht. ` +
      'Wer nur die Aufzeichnung beenden will, schaltet „Aufzeichnung aktiv“ aus.',
    )
    if (!confirmed) return
    try {
      await api.deleteSensor(sensorId)
      toast(`„${sensor.name}“ gelöscht.`)
      navigate('/sensoren')
    } catch (error) {
      toast((error as Error).message, 'err')
    }
  }

  return (
    <>
      <PageHeader
        title={sensor?.name ?? 'Sensor'}
        subtitle={sensor ? `${sensor.entity_id}${sensor.attribut ? ` → ${sensor.attribut}` : ''}` : undefined}
        actions={<Link className="btn btn-ghost" to="/sensoren"><Icon name="arrowLeft" size={16} />Zur Liste</Link>}
      />
      <div className="content form-content">
        {loadError ? <div className="alert">{loadError}</div> : null}
        {!draft && !loadError ? <div className="center"><div className="spinner" /></div> : null}
        {sensor && draft && catalog ? (
          <>
            <div className="card">
              <div className="card-body">
                <SensorFields value={draft} onChange={patch} catalog={catalog} errors={errors} showActive />
              </div>
            </div>
            <div className="card">
              <div className="card-body">
                <div className="kv-row"><span className="k">Letzter Wert</span><span className="v">{fmtValue(sensor.letzter_wert, sensor.letzter_text, sensor.einheit)}</span></div>
                <div className="kv-row"><span className="k">Zeitpunkt</span><span className="v">{sensor.letzte_zeit_text ?? 'noch kein Wert'}</span></div>
                <div className="kv-row"><span className="k">Sensor-ID (SQL)</span><span className="v mono">{sensor.id}</span></div>
              </div>
            </div>
            <div className="card">
              <div className="card-head">
                <div>
                  <h2>Löschen</h2>
                  <div className="sub">Entfernt den Sensor samt allen aufgezeichneten Werten.</div>
                </div>
                <div className="spacer" />
                <button type="button" className="btn btn-danger" onClick={() => void remove()}><Icon name="trash" size={16} />Sensor löschen</button>
              </div>
            </div>
            <div className="form-footer">
              <div className="spacer" />
              <Link className="btn btn-ghost" to="/sensoren">Abbrechen</Link>
              <button type="button" className="btn btn-primary" disabled={saving} onClick={() => void save()}>
                <Icon name="check" size={16} />{saving ? 'Speichern…' : 'Speichern'}
              </button>
            </div>
          </>
        ) : null}
      </div>
    </>
  )
}
