import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api'
import { EntityPicker, selectionKey } from '../components/EntityPicker'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { SensorFields } from '../components/SensorFields'
import { useToast } from '../components/Toast'
import type { Catalog, HaEntity, SensorDraft, SensorFieldsValue, Suggestion } from '../types'

/* Sensoren anlegen: Entitäten und Attribute aus HA wählen, je Auswahl die
   Vorschläge prüfen, dann alle in einem Schritt speichern (ganz oder gar nicht). */

function toDraft(suggestion: Suggestion): SensorDraft {
  return { ...suggestion, rolle: null, soll_ist_paar: null, anlage: null, aktiv: true }
}

export function SensorenNeu() {
  const [entities, setEntities] = useState<HaEntity[] | null>(null)
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [loadError, setLoadError] = useState('')
  const [selected, setSelected] = useState<Map<string, SensorDraft>>(new Map())
  const [errors, setErrors] = useState<Record<string, Record<string, string>>>({})
  const [bulkCategory, setBulkCategory] = useState('')
  const [bulkPlant, setBulkPlant] = useState('')
  const [saving, setSaving] = useState(false)
  const { toast } = useToast()
  const navigate = useNavigate()

  const load = useCallback(async () => {
    try {
      const [list, cat] = await Promise.all([api.haEntities(), api.catalog()])
      setEntities(list)
      setCatalog(cat)
      setLoadError('')
    } catch (error) {
      setLoadError((error as Error).message)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const toggle = (suggestion: Suggestion, checked: boolean) => {
    setSelected((current) => {
      const next = new Map(current)
      const key = selectionKey(suggestion.entity_id, suggestion.attribut)
      if (checked && !next.has(key)) next.set(key, toDraft(suggestion))
      if (!checked) next.delete(key)
      return next
    })
  }

  const patch = (key: string, changes: Partial<SensorFieldsValue>) => {
    setSelected((current) => {
      const next = new Map(current)
      const draft = next.get(key)
      if (draft) next.set(key, { ...draft, ...changes })
      return next
    })
    setErrors((current) => {
      if (!current[key]) return current
      const remaining = { ...current[key] }
      Object.keys(changes).forEach((field) => delete remaining[field])
      return { ...current, [key]: remaining }
    })
  }

  const applyToAll = () => {
    setSelected((current) => new Map([...current].map(([key, draft]) => [key, {
      ...draft,
      ...(bulkCategory ? { kategorie: bulkCategory } : {}),
      ...(bulkPlant.trim() ? { anlage: bulkPlant.trim() } : {}),
    }])))
  }

  const save = async () => {
    const keys = [...selected.keys()]
    setSaving(true)
    try {
      await api.createSensors(keys.map((key) => selected.get(key)!))
      toast(keys.length === 1 ? 'Sensor hinzugefügt – Aufzeichnung läuft.' : `${keys.length} Sensoren hinzugefügt – Aufzeichnung läuft.`)
      navigate('/sensoren')
    } catch (error) {
      const apiError = error as ApiError
      // Feldfehler kommen als „<index>.<feld>" – zurück auf die Auswahl abbilden.
      const mapped: Record<string, Record<string, string>> = {}
      Object.entries(apiError.fieldErrors ?? {}).forEach(([path, message]) => {
        const [index, field] = path.split('.')
        const key = keys[Number(index)]
        if (key) mapped[key] = { ...mapped[key], [field]: message }
      })
      setErrors(mapped)
      toast(apiError.message, 'err')
    } finally {
      setSaving(false)
    }
  }

  const drafts = [...selected.entries()]

  return (
    <>
      <PageHeader title="Sensoren hinzufügen" subtitle="Entitäten und Attribute aus Home Assistant auswählen" />
      <div className="content form-content">
        {loadError ? (
          <div className="alert">
            {loadError}{' '}
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => void load()}><Icon name="refresh" size={14} />Erneut versuchen</button>
          </div>
        ) : null}
        {!entities && !loadError ? <div className="center"><div className="spinner" /></div> : null}

        {entities && catalog ? (
          <>
            <div className="card">
              <EntityPicker
                entities={entities}
                selected={selected}
                onToggle={toggle}
              />
            </div>

            {drafts.length > 0 ? (
              <>
                <div className="section-title">Einordnung ({drafts.length})</div>
                <div className="card">
                  <div className="card-head filter-bar">
                    <span className="muted">Für alle setzen:</span>
                    <select value={bulkCategory} onChange={(event) => setBulkCategory(event.target.value)} aria-label="Kategorie für alle">
                      <option value="">Kategorie …</option>
                      {catalog.kategorien.map((entry) => <option key={entry.schluessel} value={entry.schluessel}>{entry.bezeichnung}</option>)}
                    </select>
                    <input placeholder="Anlage …" value={bulkPlant} onChange={(event) => setBulkPlant(event.target.value)} aria-label="Anlage für alle" />
                    <button type="button" className="btn btn-ghost btn-sm" onClick={applyToAll} disabled={!bulkCategory && !bulkPlant.trim()}>
                      <Icon name="check" size={14} />Übernehmen
                    </button>
                  </div>
                </div>
                {drafts.map(([key, draft]) => (
                  <div className="card" key={key}>
                    <div className="card-head">
                      <div>
                        <h2>{draft.name || draft.entity_id}</h2>
                        <div className="sub mono">{draft.entity_id}{draft.attribut ? ` → ${draft.attribut}` : ''}</div>
                      </div>
                      <div className="spacer" />
                      <button type="button" className="icon-btn danger-icon" onClick={() => toggle(draft, false)} aria-label={`${draft.name} aus der Auswahl entfernen`}>
                        <Icon name="close" />
                      </button>
                    </div>
                    <div className="card-body">
                      {errors[key]?.entity_id ? <div className="alert">{errors[key].entity_id}</div> : null}
                      <SensorFields value={draft} onChange={(changes) => patch(key, changes)} catalog={catalog} errors={errors[key]} />
                    </div>
                  </div>
                ))}
              </>
            ) : null}
          </>
        ) : null}
        <div className="form-footer">
          <span className="muted">{drafts.length === 0 ? 'Noch nichts ausgewählt.' : `${drafts.length} ausgewählt`}</span>
          <div className="spacer" />
          <Link className="btn btn-ghost" to="/sensoren">Abbrechen</Link>
          <button type="button" className="btn btn-primary" disabled={drafts.length === 0 || saving} onClick={() => void save()}>
            <Icon name="check" size={16} />{saving ? 'Speichern…' : drafts.length > 1 ? `${drafts.length} Sensoren hinzufügen` : 'Sensor hinzufügen'}
          </button>
        </div>
      </div>
    </>
  )
}
