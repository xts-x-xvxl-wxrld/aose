const WS_BASE = (() => {
  const apiBase = import.meta.env?.VITE_API_BASE_URL
  if (apiBase) {
    return apiBase.replace(/^http/, 'ws')
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api`
})()

const RECONNECT_DELAY_MS = 3000

/**
 * WebSocket client for background task completion notifications.
 *
 * Usage:
 *   const client = new TaskNotificationClient(token, (msg) => {
 *     console.log(msg.type, msg.payload)
 *   })
 *   client.connect()
 *   // later:
 *   client.disconnect()
 *
 * Message shape: { type: string, payload: object }
 * Known types: "crawl_complete", "findymail_complete"
 */
export class TaskNotificationClient {
  constructor(token, onMessage, onError) {
    this.token = token
    this.onMessage = onMessage
    this.onError = onError
    this.ws = null
    this._reconnectTimer = null
    this._intentionalClose = false
  }

  connect() {
    this._intentionalClose = false
    this._open()
  }

  disconnect() {
    this._intentionalClose = true
    clearTimeout(this._reconnectTimer)
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }

  _open() {
    const url = `${WS_BASE}/ws/tasks?token=${encodeURIComponent(this.token)}`
    this.ws = new WebSocket(url)

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        this.onMessage(data)
      } catch {
        // Ignore unparseable frames
      }
    }

    this.ws.onerror = (err) => {
      this.onError?.(err)
    }

    this.ws.onclose = () => {
      if (!this._intentionalClose) {
        this._reconnectTimer = setTimeout(() => this._open(), RECONNECT_DELAY_MS)
      }
    }
  }
}
