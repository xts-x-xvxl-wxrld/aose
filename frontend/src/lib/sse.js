const API_BASE = import.meta.env?.VITE_API_BASE_URL || '/api/v1'

export async function* streamChat({
  token,
  tenantId,
  requestId,
  payload,
}) {
  const response = await fetch(`${API_BASE}/tenants/${tenantId}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      'X-Request-ID': requestId,
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const contentType = response.headers.get('content-type') || ''
    const body = contentType.includes('application/json')
      ? await response.json()
      : await response.text()
    const detail = typeof body?.message === 'string'
      ? body.message
      : typeof body?.detail === 'string'
        ? body.detail
        : typeof body === 'string'
          ? body
          : JSON.stringify(body)
    throw new Error(detail || `Stream request failed (${response.status})`)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('Chat stream is unavailable in this browser.')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const frames = buffer.split('\n')
      buffer = frames.pop() || ''

      for (const frame of frames) {
        if (!frame.startsWith('data: ')) continue
        const rawData = frame.slice(6).trim()
        if (!rawData) continue
        if (rawData === '[DONE]') return

        let parsed
        try {
          parsed = JSON.parse(rawData)
        } catch {
          continue
        }

        if (parsed.text) {
          yield {
            type: 'text',
            text: parsed.text,
            threadId: parsed.thread_id || '',
            requestId: parsed.request_id || requestId,
          }
        }

        if (parsed.meta) {
          yield {
            type: 'meta',
            meta: parsed.meta,
          }
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
