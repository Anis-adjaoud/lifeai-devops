import { useState, useEffect, useRef } from 'react'

// Ouvre le popup OAuth Google Fit et notifie `onSuccess(userId)` une fois connecté.
export function useGoogleFitConnect(onSuccess) {
  const [status, setStatus] = useState('idle') // idle | waiting | success | blocked
  const statusRef = useRef(status)
  const onSuccessRef = useRef(onSuccess)
  const intervalRef = useRef(null)

  useEffect(() => { statusRef.current = status }, [status])
  useEffect(() => { onSuccessRef.current = onSuccess }, [onSuccess])

  useEffect(() => {
    const handler = (e) => {
      // N'accepte que les messages de notre propre origine
      if (e.origin !== window.location.origin) return
      if (e.data?.type === 'lifeai_auth_success') {
        setStatus('success')
        statusRef.current = 'success'
        setTimeout(() => onSuccessRef.current(e.data.userId), 800)
      }
    }
    window.addEventListener('message', handler)
    // Coupe aussi le polling de fallback au démontage
    return () => {
      window.removeEventListener('message', handler)
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [])

  const connect = () => {
    const popup = window.open(
      '/auth/start',
      'google-oauth',
      'width=600,height=720,left=200,top=80,resizable=yes,scrollbars=yes'
    )

    if (!popup) {
      // Popup bloquée par le navigateur — état distinct de 'idle'
      setStatus('blocked')
      statusRef.current = 'blocked'
      return
    }

    setStatus('waiting')
    statusRef.current = 'waiting'

    // Fallback si le popup se ferme sans postMessage (ex: erreur OAuth)
    intervalRef.current = setInterval(() => {
      if (popup.closed) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
        if (statusRef.current !== 'success') {
          setStatus('idle')
          onSuccessRef.current()
        }
      }
    }, 800)
  }

  return { status, connect }
}
