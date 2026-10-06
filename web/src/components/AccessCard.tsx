import { useRef, useState } from 'react'
import { Icon } from './Icon'
import { useToast } from './Toast'
import type { AccessItem } from '../types'

/* Ein LAN-Zugang: Status, Verbindungsdaten, „Neu erzeugen“ und „Sperren“.
   Ein neues Secret zeigt die Karte genau einmal – es liegt nur im Zustand
   dieser Seite und verschwindet beim Verlassen. */

interface Props {
  item: AccessItem
  host: string
  editable: boolean
  busy: boolean
  secret: string | null
  /** Gespeichert, aber erst nach einem Neustart des Add-ons wirksam. */
  warning: string | null
  onRenew: () => void
  onLock: () => void
  onHideSecret: () => void
}

function connectionRows(item: AccessItem, host: string): [string, string][] {
  const address = item.port ? `${host}:${item.port}` : null
  switch (item.schluessel) {
    case 'datenbank':
    case 'datenbank_lesen':
      return [
        ['Server', address ?? 'Port nicht freigegeben'],
        ['Datenbank', 'skytech'],
        ['Benutzer', item.benutzer ?? ''],
        ['Verbindungs-URL', address ? `postgresql://${item.benutzer}@${address}/skytech?sslmode=disable` : '–'],
      ]
    case 'grafana':
      return [['Adresse', address ? `http://${address}/` : 'Port nicht freigegeben'], ['Benutzer', item.benutzer ?? '']]
    case 'mcp':
      return [['URL', address ? `http://${address}/mcp` : 'Port nicht freigegeben'], ['Anmeldung', 'Authorization: Bearer <Token>']]
  }
}

export function AccessCard({ item, host, editable, busy, secret, warning, onRenew, onLock, onHideSecret }: Props) {
  const secretInput = useRef<HTMLInputElement>(null)
  const [copied, setCopied] = useState(false)
  const { toast } = useToast()
  const word = item.schluessel === 'mcp' ? 'Token' : 'Passwort'

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(secret ?? '')
      setCopied(true)
    } catch {
      // Im Ingress-Rahmen kann die Zwischenablage gesperrt sein: markieren statt kopieren.
      secretInput.current?.select()
      toast('Kopieren nicht erlaubt – der Text ist markiert, bitte mit Strg/Cmd+C kopieren.', 'err')
    }
  }

  const state = item.gesetzt === null
    ? <span className="pill muted">unbekannt</span>
    : <span className={`pill ${item.gesetzt ? 'ok' : 'muted'}`}>{item.gesetzt ? 'Aktiv' : 'Gesperrt'}</span>

  return (
    <div className="card section-card">
      <div className="card-head">
        <div>
          <h2>{item.bezeichnung}</h2>
          <div className="sub">Option <span className="mono">{item.option}</span></div>
        </div>
        <div className="spacer" />
        {state}
      </div>
      <div className="card-body">
        {connectionRows(item, host).map(([label, value]) => (
          <div className="kv-row" key={label}><span className="k">{label}</span><span className="v mono">{value}</span></div>
        ))}

        {warning ? <div className="alert card-actions"><Icon name="warning" size={16} />{warning}</div> : null}

        {secret ? (
          <div className="card-actions">
            <label className="field">
              <span>Neues {word}</span>
              <input ref={secretInput} className="mono" readOnly value={secret} onFocus={(event) => event.target.select()} />
              <small>Wird nicht erneut angezeigt. Jetzt kopieren und dort eintragen, wo es gebraucht wird.</small>
            </label>
            <div className="inline-actions">
              <button type="button" className="btn btn-primary btn-sm" onClick={() => void copy()}>
                <Icon name={copied ? 'check' : 'copy'} size={16} />{copied ? 'Kopiert' : 'Kopieren'}
              </button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={onHideSecret}>Ausblenden</button>
            </div>
          </div>
        ) : null}

        <div className="inline-actions card-actions">
          <button type="button" className="btn btn-ghost btn-sm" disabled={!editable || busy} onClick={onRenew}>
            <Icon name="refresh" size={16} />{busy ? 'Wird gesetzt …' : `${word} neu erzeugen`}
          </button>
          <button type="button" className="btn btn-danger btn-sm" disabled={!editable || busy || item.gesetzt === false} onClick={onLock}>
            <Icon name="close" size={16} />Sperren
          </button>
        </div>
      </div>
    </div>
  )
}
