import { useEffect, useRef, useState } from 'react'

const ROOT = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
const SDK_URL = 'https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.page.js'

/** Never request browser notification permission on page load. */
export default function MediaSubscribe() {
  const [config, setConfig] = useState(null)
  const [status, setStatus] = useState('Checking subscription availability…')
  const [sdk, setSdk] = useState(null)
  const once = useRef(false)

  useEffect(() => {
    let active = true
    fetch(ROOT + '/dic/studio/public-notifications/', {credentials:'omit',cache:'no-store'})
      .then(r => {if (!r.ok) throw new Error('Push unavailable');return r.json()})
      .then(data => {if (active) {setConfig(data);setStatus(data.enabled?'Choose to receive new DAWANA publications and live programme alerts.':'Website notifications are not configured yet.')}})
      .catch(() => {if (active) setStatus('Website subscriptions are temporarily unavailable.')})
    return () => {active=false}
  }, [])

  useEffect(() => {
    if (!config?.enabled || !config.app_id || once.current) return
    once.current = true
    let active = true
    window.OneSignalDeferred = window.OneSignalDeferred || []
    window.OneSignalDeferred.push(async OneSignal => {
      try {
        await OneSignal.init({appId:config.app_id,
          serviceWorkerPath:'OneSignalSDKWorker.js',serviceWorkerParam:{scope:'/'},
          notifyButton:{enable:false},allowLocalhostAsSecureOrigin:false})
        if (active) setSdk(OneSignal)
      } catch {if (active) setStatus('Notifications are not available in this browser.')}
    })
    if (!document.querySelector('script[data-dawana-onesignal]')) {
      const script = document.createElement('script')
      script.src = SDK_URL
      script.async = true
      script.dataset.dawanaOnesignal = 'true'
      document.head.appendChild(script)
    }
    return () => {active=false}
  }, [config])

  async function subscribe() {
    if (!sdk) return
    try {
      await sdk.Notifications.requestPermission()
      if (sdk.Notifications.permission) setStatus('Notifications enabled. You can switch them off in your browser settings.')
      else setStatus('Notifications were not enabled. You can try again in browser settings.')
    } catch {
      setStatus('Your browser could not enable notifications. On iPhone, add DAWANA to your Home Screen first.')
    }
  }

  return <section className="media-subscribe" aria-label="Subscribe to DAWANA updates">
    <div><strong>Stay informed</strong><p>{status}</p>
      <small>Notifications are optional. You can change your choice in browser or device settings. On iPhone, add this website to your Home Screen before subscribing.</small></div>
    {config?.enabled && <button type="button" disabled={!sdk} onClick={subscribe}>{sdk?'Enable notifications':'Preparing notifications…'}</button>}
  </section>
}
