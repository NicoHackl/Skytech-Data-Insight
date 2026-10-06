import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { Icon } from './Icon'
import { useToast } from './Toast'
import type { Retention } from '../types'

/* Aufbewahrung von Roh- und Minutenwerten. Leeres Feld = nie löschen.
   Der Server sichert vor jeder Änderung, weil eine kürzere Frist Daten löscht. */

const MIN_MINUTE_DAYS = 31

const toText = (days: number | null) => (days === null ? '' : String(days))

function toDays(text: string): number | null | undefined {
  const trimmed = text.trim()
  if (!trimmed) return null
  return /^\d+$/.test(trimmed) ? Number(trimmed) : undefined
}

export function RetentionCard({ onSaved }: { onSaved: () => void }) {
  const [saved, setSaved] = useState<Retention | null>(null)
  const [raw, setRaw] = useState('')
  const [minute, setMinute] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const { toast } = useToast()

  useEffect(() => {
    api.retention()
      .then((value) => {
        setSaved(value)
        setRaw(toText(value.rohwerte_tage))
        setMinute(toText(value.minutenwerte_tage))
      })
      .catch((error: Error) => toast(error.message, 'err'))
  }, [toast])

  const save = async () => {
    const rawDays = toDays(raw)
    const minuteDays = toDays(minute)
    const local: Record<string, string> = {}
    if (rawDays === undefined || rawDays === 0) local.rohwerte_tage = 'Ganze Zahl ab 1 oder leer für „nie löschen“.'
    if (minuteDays === undefined || (minuteDays !== null && minuteDays < MIN_MINUTE_DAYS)) {
      local.minutenwerte_tage = `Ganze Zahl ab ${MIN_MINUTE_DAYS} oder leer für „nie löschen“.`
    }
    setErrors(local)
    if (Object.keys(local).length > 0 || rawDays === undefined || minuteDays === undefined) return

    const shorter = (next: number | null, before: number | null | undefined) =>
      next !== null && (before === null || before === undefined || next < before)
    if ((shorter(rawDays, saved?.rohwerte_tage) || shorter(minuteDays, saved?.minutenwerte_tage)) &&
        !window.confirm('Die neue Frist ist kürzer: ältere Werte werden beim nächsten Lauf endgültig gelöscht. Vorher wird automatisch gesichert. Fortfahren?')) {
      return
    }

    setSaving(true)
    try {
      const result = await api.updateRetention({ rohwerte_tage: rawDays, minutenwerte_tage: minuteDays })
      setSaved(result)
      toast(`Aufbewahrung gespeichert, vorher gesichert (${result.sicherung}).`)
      onSaved()
    } catch (error) {
      const apiError = error as ApiError
      setErrors(apiError.fieldErrors ?? {})
      toast(apiError.message, 'err')
    } finally {
      setSaving(false)
    }
  }

  const fieldClass = (key: string) => `field${errors[key] ? ' invalid' : ''}`

  return (
    <div className="card section-card">
      <div className="card-head">
        <div>
          <h2>Aufbewahrung</h2>
          <div className="sub">Leeres Feld = nie löschen</div>
        </div>
      </div>
      <div className="card-body">
        {!saved ? <div className="center"><div className="spinner" /></div> : (
          <>
            <div className="form-grid">
              <label className={fieldClass('rohwerte_tage')}>
                <span>Rohwerte (Tage)</span>
                <input inputMode="numeric" value={raw} onChange={(event) => setRaw(event.target.value)} placeholder="nie löschen" />
                {errors.rohwerte_tage ? <small className="field-error">{errors.rohwerte_tage}</small> : <small>Jede Änderung eines Sensors</small>}
              </label>
              <label className={fieldClass('minutenwerte_tage')}>
                <span>Minutenwerte (Tage)</span>
                <input inputMode="numeric" value={minute} onChange={(event) => setMinute(event.target.value)} placeholder="nie löschen" />
                {errors.minutenwerte_tage
                  ? <small className="field-error">{errors.minutenwerte_tage}</small>
                  : <small>Mindestens {MIN_MINUTE_DAYS} Tage – die Verdichtungen rechnen 30 Tage rückwirkend</small>}
              </label>
            </div>
            <div className="hint-box">
              Die Verdichtungen (15 Minuten, Stunde, Tag) werden nie gelöscht – Auswertungen über Jahre bleiben
              möglich. Vor dem Speichern legt das Add-on automatisch eine Sicherung an.
            </div>
            <div className="inline-actions card-actions">
              <button type="button" className="btn btn-primary" disabled={saving} onClick={() => void save()}>
                <Icon name="check" size={16} />{saving ? 'Speichern…' : 'Speichern'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
