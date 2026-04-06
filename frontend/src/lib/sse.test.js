import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { streamChat } from './sse'

function makeBodyReader(lines) {
  const encoder = new TextEncoder()
  let index = 0

  return {
    getReader() {
      return {
        async read() {
          if (index >= lines.length) return { done: true, value: undefined }
          return { done: false, value: encoder.encode(`${lines[index++]}\n`) }
        },
        releaseLock: vi.fn(),
      }
    },
  }
}

function makeOkResponse(lines) {
  return {
    ok: true,
    status: 200,
    headers: { get: () => 'text/event-stream' },
    body: makeBodyReader(lines),
  }
}

function makeErrorResponse(status, payload) {
  return {
    ok: false,
    status,
    headers: { get: () => 'application/json' },
    json: async () => payload,
    text: async () => JSON.stringify(payload),
    body: null,
  }
}

describe('streamChat', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test('yields tenant-scoped text frames with thread metadata', async () => {
    fetch.mockResolvedValue(makeOkResponse([
      'data: {"text":"Hello","thread_id":"thread-1","request_id":"req-1"}',
      'data: [DONE]',
    ]))

    const events = []
    for await (const event of streamChat({
      token: 'tok',
      tenantId: 'tenant-1',
      requestId: 'req-1',
      payload: { user_message: 'hello' },
    })) {
      events.push(event)
    }

    expect(events).toEqual([
      {
        type: 'text',
        text: 'Hello',
        threadId: 'thread-1',
        requestId: 'req-1',
      },
    ])
  })

  test('yields meta frames', async () => {
    fetch.mockResolvedValue(makeOkResponse([
      'data: {"meta":{"type":"queued","workflow_run_id":"run-1"}}',
      'data: [DONE]',
    ]))

    const events = []
    for await (const event of streamChat({
      token: 'tok',
      tenantId: 'tenant-1',
      requestId: 'req-1',
      payload: { user_message: 'hello' },
    })) {
      events.push(event)
    }

    expect(events).toEqual([
      {
        type: 'meta',
        meta: { type: 'queued', workflow_run_id: 'run-1' },
      },
    ])
  })

  test('uses tenant-scoped path and request id header', async () => {
    fetch.mockResolvedValue(makeOkResponse(['data: [DONE]']))

    for await (const _event of streamChat({
      token: 'tok',
      tenantId: 'tenant-123',
      requestId: 'req-123',
      payload: { user_message: 'hello' },
    })) {
      // drain
    }

    const [url, options] = fetch.mock.calls[0]
    expect(url).toContain('/api/v1/tenants/tenant-123/chat/stream')
    expect(options.headers.Authorization).toBe('Bearer tok')
    expect(options.headers['X-Request-ID']).toBe('req-123')
  })

  test('throws formatted backend errors', async () => {
    fetch.mockResolvedValue(makeErrorResponse(409, {
      message: 'X-Request-ID was already accepted for a different chat turn payload.',
    }))

    await expect(async () => {
      for await (const _event of streamChat({
        token: 'tok',
        tenantId: 'tenant-1',
        requestId: 'req-1',
        payload: { user_message: 'hello' },
      })) {
        // drain
      }
    }).rejects.toThrow('already accepted')
  })
})
