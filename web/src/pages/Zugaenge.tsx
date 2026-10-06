import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { AccessCard } from '../components/AccessCard'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { useToast } from '../components/Toast'
import type { AccessItem, AccessKey, AccessResponse } from '../types'

/* Zugänge (M3, D-025): Verbindungsdaten für VSCode, Grafana im LAN und MCP;
   Passwörter und Token neu erzeugen oder sperren – wirksam ohne Neustart. */

const CONSEQUENCE: Record<AccessKey, string> = {
  datenbank: 'Gespeicherte Verbindungen (z. B. VSCode) mit Vollzugriff müssen danach das neue Passwort bekommen.',
  datenbank_lesen: 'Gespeicherte Verbindungen mit Lesezugriff müssen danach das neue Passwort bekommen.',
  grafana: 'Die Anmeldung an Grafana im LAN (Port 3000) braucht danach das neue Passwort. Über Home Assistant bleibt Grafana erreichbar.',
  mcp: 'Der MCP-Server startet kurz neu. Alle MCP-Clients (Claude, ChatGPT …) müssen das neue Token eintragen.',
}

export function Zugaenge() {
  const [data, setData] = useState<AccessResponse | null>(null)
  const [loadError, setLoadError] = useState('')
  const [busy, setBusy] = useState<AccessKey | null>(null)
  const [secrets, setSecrets] = useState<Partial<Record<AccessKey, string>>>({})
  const [warnings, setWarnings] = useState<Partial<Record<AccessKey, string>>>({})
  const { toast } = useToast()

  const load = useCallback(async () => {
    try {
      setData(await api.access())
      setLoadError('')
    } catch (error) {
      setLoadError((error as Error).message)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const change = async (item: AccessItem, action: 'neu' | 'sperren') => {
    const question = action === 'neu'
      ? `Für „${item.bezeichnung}“ neu erzeugen?\n\nDas bisherige gilt ab sofort nicht mehr. ${CONSEQUENCE[item.schluessel]}`
      : `„${item.bezeichnung}“ sperren?\n\nAnmeldungen über das Netz sind danach nicht mehr möglich. ${CONSEQUENCE[item.schluessel]}`
    if (!window.confirm(question)) return
    setBusy(item.schluessel)
    try {
      const result = await api.changeAccess(item.schluessel, action)
      if (result.secret) setSecrets((current) => ({ ...current, [item.schluessel]: result.secret ?? undefined }))
      setWarnings((current) => ({ ...current, [item.schluessel]: result.warnung ?? undefined }))
      if (result.warnung) toast('Gespeichert, aber noch nicht wirksam – siehe Hinweis in der Karte.', 'err')
      else toast(action === 'neu' ? 'Neu erzeugt und sofort wirksam.' : 'Gesperrt.')
      await load()
    } catch (error) {
      toast((error as Error).message, 'err')
    } finally {
      setBusy(null)
    }
  }

  const hideSecret = (key: AccessKey) => setSecrets(({ [key]: _hidden, ...rest }) => rest)

  return (
    <>
      <PageHeader title="Zugänge" subtitle="Datenbank, Grafana und MCP im LAN" />
      <div className="content">
        {loadError ? <div className="alert">{loadError}</div> : null}
        {!data && !loadError ? <div className="center"><div className="spinner" /></div> : null}
        {data ? (
          <>
            {!data.verfuegbar ? (
              <div className="info-strip"><Icon name="info" size={16} />Ändern ist nur im Add-on unter Home Assistant möglich.</div>
            ) : null}
            <div className="hint-box">
              Ports werden im Abschnitt „Netzwerk“ der Add-on-Seite freigegeben oder abgeschaltet. Keinen dieser Ports
              ins Internet freigeben – die Verbindungen sind unverschlüsselt.
              {data.host ? null : ' Die Adresse des HA-Hosts ließ sich nicht ermitteln; statt <ha-adresse> die IP von Home Assistant einsetzen.'}
            </div>
            {data.zugaenge.map((item) => (
              <AccessCard
                key={item.schluessel}
                item={item}
                host={data.host ?? '<ha-adresse>'}
                editable={data.verfuegbar}
                busy={busy === item.schluessel}
                secret={secrets[item.schluessel] ?? null}
                warning={warnings[item.schluessel] ?? null}
                onRenew={() => void change(item, 'neu')}
                onLock={() => void change(item, 'sperren')}
                onHideSecret={() => hideSecret(item.schluessel)}
              />
            ))}
          </>
        ) : null}
      </div>
    </>
  )
}
