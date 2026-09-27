import { useId } from 'react'
import type { Catalog, Rolle, SensorFieldsValue } from '../types'

/* Die bearbeitbaren Felder eines Sensors. Benutzt beim Anlegen (je
   ausgewähltem Sensor eine Karte) und beim Bearbeiten — eine Quelle für
   „welche Felder hat ein Sensor". Fehler kommen feldweise vom Server. */

interface Props {
  value: SensorFieldsValue
  onChange: (patch: Partial<SensorFieldsValue>) => void
  catalog: Catalog
  errors?: Record<string, string>
  showActive?: boolean
}

function FieldError({ message }: { message?: string }) {
  return message ? <small className="field-error">{message}</small> : null
}

const emptyToNull = (text: string) => (text.trim() ? text : null)

export function SensorFields({ value, onChange, catalog, errors = {}, showActive = false }: Props) {
  const id = useId()
  const fieldClass = (key: string) => `field${errors[key] ? ' invalid' : ''}`

  return (
    <div className="form-grid">
      <label className={`${fieldClass('name')} wide`}>
        <span>Name <em>*</em></span>
        <input value={value.name} onChange={(event) => onChange({ name: event.target.value })} />
        <FieldError message={errors.name} />
      </label>

      <label className={fieldClass('kategorie')}>
        <span>Kategorie <em>*</em></span>
        <select value={value.kategorie} onChange={(event) => onChange({ kategorie: event.target.value })}>
          {catalog.kategorien.map((entry) => <option key={entry.schluessel} value={entry.schluessel}>{entry.bezeichnung}</option>)}
        </select>
        <FieldError message={errors.kategorie} />
      </label>

      <label className={fieldClass('groesse')}>
        <span>Größe <em>*</em></span>
        <select value={value.groesse} onChange={(event) => onChange({ groesse: event.target.value })}>
          {catalog.groessen.map((entry) => <option key={entry.schluessel} value={entry.schluessel}>{entry.bezeichnung}</option>)}
        </select>
        <FieldError message={errors.groesse} />
      </label>

      <label className={fieldClass('einheit')}>
        <span>Einheit</span>
        <input value={value.einheit ?? ''} onChange={(event) => onChange({ einheit: emptyToNull(event.target.value) })} placeholder="z. B. W, kWh, °C" />
        <FieldError message={errors.einheit} />
      </label>

      <label className={fieldClass('anlage')}>
        <span>Anlage</span>
        <input list={`${id}-anlagen`} value={value.anlage ?? ''} onChange={(event) => onChange({ anlage: emptyToNull(event.target.value) })} placeholder="z. B. Dach Süd, Wärmepumpe" />
        <datalist id={`${id}-anlagen`}>{catalog.anlagen.map((anlage) => <option key={anlage} value={anlage} />)}</datalist>
        <small>Fasst Sensoren einer Anlage zusammen (Filter in SQL und Grafana).</small>
        <FieldError message={errors.anlage} />
      </label>

      <label className={fieldClass('rolle')}>
        <span>Rolle</span>
        <select
          value={value.rolle ?? ''}
          onChange={(event) => {
            const rolle = (event.target.value || null) as Rolle
            onChange(rolle ? { rolle } : { rolle, soll_ist_paar: null })
          }}
        >
          <option value="">–</option>
          <option value="ist">Ist-Wert</option>
          <option value="soll">Soll-Wert</option>
        </select>
        <FieldError message={errors.rolle} />
      </label>

      <label className={fieldClass('soll_ist_paar')}>
        <span>Soll/Ist-Paar</span>
        <input
          list={`${id}-paare`}
          value={value.soll_ist_paar ?? ''}
          disabled={!value.rolle}
          onChange={(event) => onChange({ soll_ist_paar: emptyToNull(event.target.value) })}
          placeholder={value.rolle ? 'z. B. Heizstab Leistung' : 'erst Rolle wählen'}
        />
        <datalist id={`${id}-paare`}>{catalog.paare.map((paar) => <option key={paar} value={paar} />)}</datalist>
        <small>Soll und Ist mit gleichem Paarnamen erscheinen gemeinsam in v_soll_ist.</small>
        <FieldError message={errors.soll_ist_paar} />
      </label>

      <div className="wide inline-actions">
        <label className="switch">
          <input type="checkbox" checked={value.energie_zaehler} onChange={(event) => onChange({ energie_zaehler: event.target.checked })} />
          <span className="track" />
          <span className="switch-label">Zählerstand<small>Minutenwerte tragen den Zuwachs (z. B. Energie in kWh).</small></span>
        </label>
        {showActive ? (
          <label className="switch">
            <input type="checkbox" checked={value.aktiv} onChange={(event) => onChange({ aktiv: event.target.checked })} />
            <span className="track" />
            <span className="switch-label">Aufzeichnung aktiv<small>Aus: keine neuen Werte, vorhandene bleiben.</small></span>
          </label>
        ) : null}
      </div>
    </div>
  )
}
