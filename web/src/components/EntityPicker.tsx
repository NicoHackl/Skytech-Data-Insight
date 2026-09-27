import { useMemo, useState } from 'react'
import { Icon } from './Icon'
import type { HaEntity, Suggestion } from '../types'

/* Auswahl von HA-Entitäten und Attributen. Kennt nur Auswahl und Anzeige;
   was aus der Auswahl wird, entscheidet die Seite. Schlüssel einer Auswahl:
   „entity_id|attribut" (Attribut leer = Zustand). */

export const selectionKey = (entityId: string, attribute: string | null) => `${entityId}|${attribute ?? ''}`

const MAX_ROWS = 150
const NUMERIC_STATES = new Set(['on', 'off'])

function isNumericState(state: string | null): boolean {
  if (state === null) return false
  return NUMERIC_STATES.has(state) || (state.trim() !== '' && Number.isFinite(Number(state)))
}

interface Props {
  entities: HaEntity[]
  selected: Map<string, Suggestion>
  onToggle: (suggestion: Suggestion, checked: boolean) => void
}

export function EntityPicker({ entities, selected, onToggle }: Props) {
  const [filter, setFilter] = useState('')
  const [domain, setDomain] = useState('')
  const [numericOnly, setNumericOnly] = useState(true)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const domains = useMemo(() => [...new Set(entities.map((entity) => entity.domain))].sort(), [entities])

  const matches = useMemo(() => {
    const needle = filter.trim().toLowerCase()
    return entities.filter((entity) =>
      (!domain || entity.domain === domain)
      && (!numericOnly || isNumericState(entity.state) || entity.attribute.length > 0)
      && (!needle || entity.entity_id.includes(needle) || entity.name.toLowerCase().includes(needle)))
  }, [entities, filter, domain, numericOnly])

  const toggleExpanded = (entityId: string) => {
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(entityId)) next.delete(entityId)
      else next.add(entityId)
      return next
    })
  }

  return (
    <>
      <div className="card-head filter-bar">
        <input type="search" placeholder="Suchen: Name oder Entität …" value={filter} onChange={(event) => setFilter(event.target.value)} aria-label="Entitäten durchsuchen" autoFocus />
        <select value={domain} onChange={(event) => setDomain(event.target.value)} aria-label="Nach Bereich filtern">
          <option value="">Alle Bereiche</option>
          {domains.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
        <label className="switch">
          <input type="checkbox" checked={numericOnly} onChange={(event) => setNumericOnly(event.target.checked)} />
          <span className="track" />
          <span className="switch-label">Nur Zahlenwerte</span>
        </label>
      </div>
      <div className="pick-list">
        {matches.slice(0, MAX_ROWS).map((entity) => {
          const key = selectionKey(entity.entity_id, null)
          const open = expanded.has(entity.entity_id)
          const openAttributes = entity.attribute.filter((attribute) => !attribute.erfasst)
          return (
            <div className="pick-entity" key={entity.entity_id}>
              <div className="pick-row">
                <input
                  type="checkbox"
                  checked={entity.erfasst || selected.has(key)}
                  disabled={entity.erfasst}
                  onChange={(event) => onToggle(entity.vorschlag, event.target.checked)}
                  aria-label={`${entity.name} auswählen`}
                />
                <div className="pick-main">
                  <span className="cell-title">{entity.name}</span>
                  <span className="cell-sub mono">{entity.entity_id}</span>
                </div>
                <span className="pick-state">{entity.state ?? '–'}{entity.einheit ? ` ${entity.einheit}` : ''}</span>
                {entity.erfasst ? <span className="pill ok">erfasst</span> : null}
                {entity.attribute.length > 0 ? (
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => toggleExpanded(entity.entity_id)} aria-expanded={open}>
                    <Icon name={open ? 'up' : 'down'} size={14} />Attribute ({entity.attribute.length})
                  </button>
                ) : null}
              </div>
              {open ? (
                <div className="pick-attributes">
                  {openAttributes.length > 1 ? (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => openAttributes.forEach((attribute) => onToggle(attribute.vorschlag, true))}
                    >
                      <Icon name="check" size={14} />Alle Attribute übernehmen
                    </button>
                  ) : null}
                  {entity.attribute.map((attribute) => {
                    const attributeKey = selectionKey(entity.entity_id, attribute.name)
                    return (
                      <label className="pick-row pick-attribute" key={attribute.name}>
                        <input
                          type="checkbox"
                          checked={attribute.erfasst || selected.has(attributeKey)}
                          disabled={attribute.erfasst}
                          onChange={(event) => onToggle(attribute.vorschlag, event.target.checked)}
                        />
                        <span className="pick-main mono">{attribute.name}</span>
                        <span className="pick-state">{String(attribute.wert)}</span>
                        {attribute.erfasst ? <span className="pill ok">erfasst</span> : null}
                      </label>
                    )
                  })}
                </div>
              ) : null}
            </div>
          )
        })}
        {matches.length === 0 ? <div className="empty">Keine Entität passt zum Filter.</div> : null}
        {matches.length > MAX_ROWS ? (
          <div className="info-strip pick-more">
            <Icon name="info" size={16} />
            {matches.length - MAX_ROWS} weitere Treffer – bitte Suche oder Bereich eingrenzen.
          </div>
        ) : null}
      </div>
    </>
  )
}
