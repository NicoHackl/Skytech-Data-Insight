import { useCallback, useEffect, useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import { api, BACKUP_ARCHIVE_PATH, backupFilePath } from '../api'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/Layout'
import { useToast } from '../components/Toast'
import { fmtBytes } from '../format'
import type { BackupsResponse, UploadResult } from '../types'

/* Sicherungen (M2): Komplettpaket herunterladen, Sicherung hochladen und
   einspielen, lokale Sicherungen verwalten. Eine Wiederherstellung startet das
   Add-on teilweise neu – die Seite fragt danach so lange nach, bis der Dienst
   wieder antwortet. */

const POLL_MS = 3000

export function Sicherungen() {
  const [data, setData] = useState<BackupsResponse | null>(null)
  const [loadError, setLoadError] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [uploaded, setUploaded] = useState<UploadResult | null>(null)
  const [drag, setDrag] = useState(false)
  const [restoring, setRestoring] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const { toast } = useToast()

  const load = useCallback(async () => {
    try {
      const response = await api.backups()
      setData(response)
      setLoadError('')
      return response
    } catch (error) {
      setLoadError((error as Error).message)
      return null
    }
  }, [])

  useEffect(() => { void load() }, [load])

  // Während einer Wiederherstellung (inklusive Neustart des Dienstes) nachfragen.
  useEffect(() => {
    if (!restoring) return
    const timer = window.setInterval(async () => {
      const response = await load()
      const state = response?.wiederherstellung
      if (response && !response.laeuft && state && state.status !== 'laeuft') {
        setRestoring(false)
        if (state.status === 'erfolgreich') toast('Sicherung eingespielt – Aufzeichnung läuft wieder.')
        else toast(state.meldung ?? 'Wiederherstellung fehlgeschlagen.', 'err')
      }
    }, POLL_MS)
    return () => window.clearInterval(timer)
  }, [restoring, load, toast])

  const run = async (key: string, action: () => Promise<unknown>, success: string) => {
    setBusy(key)
    try {
      await action()
      toast(success)
      await load()
    } catch (error) {
      toast((error as Error).message, 'err')
    } finally {
      setBusy(null)
    }
  }

  const upload = async (file: File | undefined) => {
    if (!file) return
    setBusy('upload')
    setUploaded(null)
    try {
      setUploaded(await api.uploadBackup(file))
      await load()
    } catch (error) {
      toast((error as Error).message, 'err')
    } finally {
      setBusy(null)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  const restore = async (name: string, label: string) => {
    const confirmed = window.confirm(
      `„${label}“ wirklich einspielen?\n\nDie aktuelle Datenbank wird vollständig ersetzt. Vorher wird automatisch ` +
      'eine Sicherung des jetzigen Stands angelegt. Aufzeichnung und MCP-Server starten dabei kurz neu.',
    )
    if (!confirmed) return
    try {
      await api.restoreBackup(name)
      setUploaded(null)
      setRestoring(true)
    } catch (error) {
      toast((error as Error).message, 'err')
    }
  }

  const remove = (name: string) => {
    if (!window.confirm(`Sicherung „${name}“ löschen?`)) return
    void run(name, () => api.deleteBackup(name), 'Sicherung gelöscht.')
  }

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault()
    setDrag(false)
    void upload(event.dataTransfer.files[0])
  }

  const state = data?.wiederherstellung
  const inProgress = restoring || data?.laeuft

  return (
    <>
      <PageHeader title="Sicherungen" subtitle="Herunterladen, einspielen, verwalten" />
      <div className="content">
        {loadError && !inProgress ? <div className="alert">{loadError}</div> : null}

        {inProgress ? (
          <div className="info-strip">
            <div className="spinner" />
            Wiederherstellung läuft – die Seite aktualisiert sich selbst. Bitte nicht schließen.
          </div>
        ) : null}
        {!inProgress && state && state.status !== 'laeuft' ? (
          <div className={state.status === 'erfolgreich' ? 'info-strip' : 'alert'}>
            <Icon name={state.status === 'erfolgreich' ? 'check' : 'warning'} size={16} />
            Letzte Wiederherstellung ({state.beendet ?? state.gestartet}, {state.datei}): {state.meldung}
          </div>
        ) : null}

        <div className="card section-card">
          <div className="card-head">
            <div>
              <h2>Komplette Sicherung herunterladen</h2>
              <div className="sub">Datenbank und Grafana-Dashboards als eine .tar-Datei – unabhängig von Home Assistant</div>
            </div>
            <div className="spacer" />
            <a className="btn btn-primary btn-sm" href={BACKUP_ARCHIVE_PATH} download>
              <Icon name="download" size={16} />Herunterladen
            </a>
          </div>
          <div className="card-body">
            <div className="hint-box">
              Home-Assistant-Backups enthalten die Daten ebenfalls: vor jedem HA-Backup legt das Add-on einen
              Datenbank-Dump an, nach einer Wiederherstellung spielt es ihn beim Start automatisch ein.
            </div>
          </div>
        </div>

        <div className="card section-card">
          <div className="card-head">
            <div>
              <h2>Sicherung einspielen</h2>
              <div className="sub">.tar aus dem Download oder .dump (pg_dump, Format custom)</div>
            </div>
          </div>
          <div className="card-body">
            <label
              className={`dropzone${drag ? ' drag' : ''}`}
              onDragOver={(event) => { event.preventDefault(); setDrag(true) }}
              onDragLeave={() => setDrag(false)}
              onDrop={onDrop}
            >
              <input ref={fileInput} type="file" accept=".tar,.dump" hidden disabled={busy === 'upload' || !!inProgress}
                onChange={(event: ChangeEvent<HTMLInputElement>) => void upload(event.target.files?.[0])} />
              {busy === 'upload' ? <div className="spinner" /> : <Icon name="upload" size={28} />}
              <strong>{busy === 'upload' ? 'Wird hochgeladen und geprüft …' : 'Datei hierher ziehen oder klicken'}</strong>
              <span>Die Datei wird zuerst nur geprüft – eingespielt wird erst nach Bestätigung.</span>
            </label>

            {uploaded ? (
              <div className="upload-result">
                <div className="kv-row"><span className="k">Datei</span><span className="v">{uploaded.original}</span></div>
                <div className="kv-row"><span className="k">Größe</span><span className="v">{fmtBytes(uploaded.groesse_bytes)}</span></div>
                {uploaded.beschreibung?.erstellt ? (
                  <div className="kv-row"><span className="k">Erstellt</span><span className="v">{uploaded.beschreibung.erstellt}</span></div>
                ) : null}
                {uploaded.beschreibung?.version ? (
                  <div className="kv-row"><span className="k">Add-on-Version</span><span className="v">{uploaded.beschreibung.version}</span></div>
                ) : null}
                <div className="kv-row"><span className="k">Inhalt</span><span className="v">Datenbank{uploaded.grafana ? ' und Grafana' : ''}</span></div>
                <div className="inline-actions card-actions">
                  <button type="button" className="btn btn-danger" disabled={!!inProgress}
                    onClick={() => void restore(uploaded.datei, uploaded.original)}>
                    <Icon name="refresh" size={16} />Jetzt einspielen
                  </button>
                  <button type="button" className="btn btn-ghost" onClick={() => setUploaded(null)}>Abbrechen</button>
                </div>
              </div>
            ) : null}
          </div>
        </div>

        <div className="card section-card">
          <div className="card-head">
            <div>
              <h2>Lokale Sicherungen</h2>
              <div className="sub">Unter /data/backup – automatisch vor MCP-Änderungen und Wiederherstellungen, dazu manuelle</div>
            </div>
            <div className="spacer" />
            <button type="button" className="btn btn-ghost btn-sm" disabled={busy === 'create' || !!inProgress}
              onClick={() => void run('create', api.createBackup, 'Sicherung angelegt.')}>
              <Icon name="plus" size={16} />{busy === 'create' ? 'Wird angelegt …' : 'Jetzt sichern'}
            </button>
          </div>
          {!data && !loadError ? <div className="center"><div className="spinner" /></div> : null}
          {data && data.sicherungen.length === 0 ? <div className="empty">Noch keine lokalen Sicherungen.</div> : null}
          {data && data.sicherungen.length > 0 ? (
            <div className="table-wrap">
              <table className="data static-rows">
                <thead>
                  <tr><th>Erstellt</th><th>Art</th><th>Größe</th><th /></tr>
                </thead>
                <tbody>
                  {data.sicherungen.map((item) => (
                    <tr key={item.datei}>
                      <td><span className="cell-title">{item.erstellt}</span><span className="cell-sub mono">{item.datei}</span></td>
                      <td>{item.art_text}</td>
                      <td>{fmtBytes(item.groesse_bytes)}</td>
                      <td>
                        <div className="row-actions">
                          <a className="icon-btn" href={backupFilePath(item.datei)} download aria-label={`${item.datei} herunterladen`} title="Herunterladen">
                            <Icon name="download" />
                          </a>
                          <button type="button" className="icon-btn" disabled={!!inProgress}
                            onClick={() => void restore(item.datei, `${item.art_text} vom ${item.erstellt}`)}
                            aria-label={`${item.datei} einspielen`} title="Einspielen">
                            <Icon name="refresh" />
                          </button>
                          <button type="button" className="icon-btn danger-icon" disabled={busy === item.datei || !!inProgress}
                            onClick={() => remove(item.datei)} aria-label={`${item.datei} löschen`} title="Löschen">
                            <Icon name="trash" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      </div>
    </>
  )
}
