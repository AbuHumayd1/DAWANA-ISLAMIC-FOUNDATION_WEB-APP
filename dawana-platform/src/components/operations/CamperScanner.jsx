import { useEffect, useRef, useState } from 'react'
import { getOperationsData, postOperationsData } from '../../services/operationsApi'
import { checkInTime } from '../../services/checkIn'
import { scanToken, movementPath, scanPath, stopCamera } from '../../services/camperMovement'
import { createQrDecoder, cameraErrorMessage } from '../../services/qrDecoder'
import './CamperScanner.css'

export default function CamperScanner({ edition, user, participant = null, onClose, onSaved }) {
  const [preview, setPreview] = useState(null), [error, setError] = useState(''), [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false), [cameraOn, setCameraOn] = useState(false)
  const [devices, setDevices] = useState([]), [camera, setCamera] = useState('')
  const [lockedAction, setLockedAction] = useState('')
  const [reason, setReason] = useState(''), [reference, setReference] = useState(''), [authorized, setAuthorized] = useState(false)
  const video = useRef(null), stream = useRef(null), timer = useRef(null), generation = useRef(0)
  const decoder = useRef(null)
  const token = useRef(''), request = useRef(null), alive = useRef(true), pending = useRef(false)
  const permissions = user.permissions
  function stop() {
    generation.current += 1; clearTimeout(timer.current); stopCamera(stream.current); stream.current = null
    decoder.current?.destroy(); decoder.current = null
    if (video.current) video.current.srcObject = null
    setCameraOn(false)
  }
  useEffect(() => {
    alive.current = true
    const hide = () => { if (document.hidden) { generation.current += 1; clearTimeout(timer.current); stopCamera(stream.current); stream.current = null; decoder.current?.destroy(); decoder.current = null; if (video.current) video.current.srcObject = null; setCameraOn(false) } }
    document.addEventListener('visibilitychange', hide)
    return () => { alive.current = false; generation.current += 1; clearTimeout(timer.current); stopCamera(stream.current); decoder.current?.destroy(); decoder.current = null; token.current = ''; document.removeEventListener('visibilitychange', hide) }
  }, [])
  useEffect(() => {
    if (!participant) return
    const controller = new AbortController()
    getOperationsData(movementPath(edition, participant.participant_id), { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setPreview({ ...participant, ...data }) })
      .catch(() => { if (!controller.signal.aborted) setError('Movement history could not be loaded. Check your access or retry manual lookup.') })
    return () => controller.abort()
  }, [edition, participant])
  async function resolve(value) {
    stop(); setError(''); setNotice(''); setPreview(null); request.current = null; setLockedAction('')
    let decoded
    try { decoded = scanToken(value) } catch (failure) { setError(failure.message); return }
    token.current = decoded; setBusy(true)
    try {
      const result = await postOperationsData(scanPath(edition), { action: 'preview', token: decoded })
      if (alive.current) { setPreview(result); setAuthorized(false); setReference(''); setReason('') }
    } catch { if (alive.current) { token.current = ''; setError('ID unavailable. Check the selected edition, staff permissions and card validity, then rescan.') } }
    finally { if (alive.current) setBusy(false) }
  }
  async function start(deviceId = camera) {
    stop(); setError(''); setNotice(''); setPreview(null); token.current = ''; request.current = null; setLockedAction('')
    const attempt = generation.current
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) { setError('Camera scanning needs HTTPS and a supported browser. Use manual lookup or paste a QR below.'); return }
    try {
      const reader = await createQrDecoder()
      if (!alive.current || attempt !== generation.current) { reader.destroy(); return }
      decoder.current = reader
      const capture = await navigator.mediaDevices.getUserMedia({ video: deviceId ? { deviceId: { exact: deviceId } } : { facingMode: { ideal: 'environment' } }, audio: false })
      if (!alive.current || attempt !== generation.current) { stopCamera(capture); return }
      stream.current = capture; video.current.srcObject = capture; await video.current.play()
      if (!alive.current || attempt !== generation.current) { stopCamera(capture); return }
      setCameraOn(true)
      const track = capture.getVideoTracks()[0]
      track?.addEventListener('ended', () => {
        if (alive.current && attempt === generation.current) { stop(); setError('The camera disconnected. Choose another device or use manual lookup.') }
      }, { once: true })
      let cameras = []
      try { cameras = await navigator.mediaDevices.enumerateDevices() }
      catch { if (alive.current && attempt === generation.current) setNotice('Camera is active; camera selection is unavailable in this browser.') }
      if (!alive.current || attempt !== generation.current) return
      setDevices(cameras.filter(device => device.kind === 'videoinput'))
      const activeId = track?.getSettings?.().deviceId
      if (activeId && cameras.some(device => device.deviceId === activeId)) setCamera(activeId)
      const detect = async () => {
        if (!alive.current || attempt !== generation.current) return
        try {
          const value = await reader.decode(video.current)
          if (!alive.current || attempt !== generation.current) return
          if (value) { await resolve(value); return }
        } catch (failure) {
          if (alive.current && attempt === generation.current) { stop(); setError(cameraErrorMessage(failure)) }
          return
        }
        if (attempt === generation.current) timer.current = setTimeout(detect, 250)
      }
      timer.current = setTimeout(detect, 250)
    } catch (failure) {
      if (!alive.current || attempt !== generation.current) return
      stop(); setError(cameraErrorMessage(failure))
    }
  }
  async function record(action) {
    if (pending.current || busy || !preview) return
    if (!window.confirm(`${action === 'arrive' ? 'Record initial arrival' : action === 'departure' ? 'Confirm authorized departure' : 'Confirm return'} for ${preview.name}?`)) return
    pending.current = true; setBusy(true); stop(); setError(''); setNotice('')
    const payload = { action, confirmed: true, expected_version: preview.version, reason,
      authorization_reference: reference, authorization_checked: authorized }
    // Keep the exact payload/key after an uncertain response. Changing fields needs a fresh preview.
    try {
      if (!request.current) { request.current = { ...payload, request_id: crypto.randomUUID() }; setLockedAction(action) }
      const result = token.current
        ? await postOperationsData(scanPath(edition), { ...request.current, token: token.current })
        : await postOperationsData(movementPath(edition, preview.participant_id), { ...request.current, participant_id: preview.participant_id })
      if (alive.current) {
        const message = `${result.created ? 'Saved' : 'Already saved'} · ${checkInTime(result.check_in?.time || result.event?.time)}`
        setNotice(message)
        setPreview(null); token.current = ''; request.current = null; onSaved?.(message)
      }
    } catch {
      if (alive.current) setError('Could not confirm the outcome. Retry the same request, or close and refresh the camper history before starting a different action.')
    } finally { pending.current = false; if (alive.current) setBusy(false) }
  }
  return <section className="ops-panel camper-scanner" aria-label="Camper scanning and movement">
    <header><h2>{participant ? `Movements: ${participant.name}` : 'Scan camper ID'}</h2><button type="button" disabled={busy} onClick={() => { stop(); onClose() }}>Close</button></header>
    {!participant && <>
      <p>Scanning only previews an ID. Confirm each arrival, authorized departure or return separately.</p>
      <div className="camper-camera-frame"><video ref={video} muted playsInline aria-label="QR camera preview" /><span aria-hidden="true" /></div>
      <button type="button" disabled={busy} onClick={() => start()}>Start camera</button>
      <button type="button" onClick={stop}>Stop camera</button>
      <span role="status">{cameraOn ? 'Camera active — place one QR inside the frame.' : 'Camera stopped.'}</span>
      {devices.length > 0 && <label>Camera<select value={camera} disabled={busy} onChange={event => { setCamera(event.target.value); start(event.target.value) }}><option value="">Rear camera (preferred)</option>{devices.map((device, index) => <option key={device.deviceId} value={device.deviceId}>{device.label || `Camera ${index + 1}`}</option>)}</select></label>}
      <form onSubmit={event => { event.preventDefault(); const input = event.currentTarget.elements.qr; const value = input.value; input.value = ''; resolve(value) }}><label>Paste camper QR link or token<input name="qr" autoComplete="off" spellCheck={false} type="password" required maxLength={2048} /></label><button disabled={busy}>Preview ID</button></form>
    </>}
    {busy && <p role="status">Checking server…</p>}{error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {preview && <div className="camper-scan-result"><h3>{preview.name}</h3><p>{preview.participant_number}</p>
      <p>{preview.check_in ? `Initial arrival: ${checkInTime(preview.check_in.time)} · ${preview.check_in.staff}` : 'Not yet checked in'}</p>
      {preview.presence && <p>Presence: <strong>{preview.presence.replaceAll('_', ' ')}</strong></p>}
      {!participant && !preview.check_in && permissions.check_in && <button disabled={busy || Boolean(lockedAction && lockedAction !== 'arrive')} onClick={() => record('arrive')}>Confirm initial check-in</button>}
      {permissions.movement_view && permissions.movement_record && <>
        <label>Reason (optional)<textarea maxLength={1000} disabled={busy || Boolean(lockedAction)} value={reason} onChange={event => setReason(event.target.value)} /></label>
        {preview.presence === 'inside' && permissions.authorize_departure && <>
          <label>Approved release authorization reference<input maxLength={160} disabled={busy || Boolean(lockedAction)} value={reference} onChange={event => setReference(event.target.value)} /></label>
          <label><input type="checkbox" disabled={busy || Boolean(lockedAction)} checked={authorized} onChange={event => setAuthorized(event.target.checked)} />I have checked the approved release authority, including collection/guardian evidence where required.</label>
          <button disabled={busy || !authorized || !reference.trim()} onClick={() => record('departure')}>Confirm departure</button>
        </>}
        {preview.presence === 'inside' && !permissions.authorize_departure && <p>A separately authorized release officer must record departure.</p>}
        {preview.presence === 'outside' && <button disabled={busy} onClick={() => record('return')}>Confirm return</button>}
      </>}
      {permissions.movement_view && preview.history && <><h3>Movement history</h3>{preview.history.length ? <ol>{preview.history.map(event => <li key={event.id}>{event.kind} · {checkInTime(event.time)} · {event.staff}{event.reason && <p>{event.reason}</p>}{event.authorization_reference && <p>Authorization: {event.authorization_reference}</p>}</li>)}</ol> : <p>No departure or return recorded.</p>}</>}
    </div>}
  </section>
}
