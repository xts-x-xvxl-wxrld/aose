import { useEffect, useState, useCallback } from 'react'
import { useAuthStore } from '@/stores/authStore'
import { TaskNotificationClient } from '@/lib/ws'

const DISMISS_AFTER_MS = 6000

// Pipeline completion events persist longer — user should see them
const PIPELINE_DISMISS_MS = 12000

/**
 * useTaskNotifications — manages WebSocket connection to /ws/tasks.
 *
 * Returns a list of active notifications (auto-dismissed after 6s).
 * Known notification types: "crawl_complete", "findymail_complete"
 */
export function useTaskNotifications() {
  const token = useAuthStore((s) => s.token)
  const [notifications, setNotifications] = useState([])

  const dismiss = useCallback((id) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id))
  }, [])

  useEffect(() => {
    if (!token) return

    const client = new TaskNotificationClient(
      token,
      (msg) => {
        const id = crypto.randomUUID()
        const notification = {
          id,
          type:    msg.type,
          payload: msg.payload || {},
          at:      new Date().toISOString(),
        }
        setNotifications((prev) => [notification, ...prev].slice(0, 5))
        const ttl = (msg.type === 'pipeline_complete' || msg.type === 'pipeline_blocked')
          ? PIPELINE_DISMISS_MS
          : DISMISS_AFTER_MS
        setTimeout(() => dismiss(id), ttl)
      },
      // errors are silently ignored — WS is best-effort
    )

    client.connect()
    return () => client.disconnect()
  }, [token, dismiss])

  return { notifications, dismiss }
}
