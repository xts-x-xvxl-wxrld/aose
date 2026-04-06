import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'
import { TaskNotificationClient } from './ws.js'

// ── WebSocket mock ─────────────────────────────────────────────────────────────

class MockWebSocket {
  constructor(url) {
    this.url = url
    this.readyState = WebSocket.CONNECTING
    this.onmessage = null
    this.onerror = null
    this.onclose = null
    MockWebSocket.instances.push(this)
  }

  close() {
    this.readyState = WebSocket.CLOSED
    this.onclose?.()
  }

  static instances = []
  static reset() {
    MockWebSocket.instances = []
  }
}
MockWebSocket.CONNECTING = 0
MockWebSocket.OPEN = 1
MockWebSocket.CLOSED = 3

// ── setup / teardown ───────────────────────────────────────────────────────────

beforeEach(() => {
  MockWebSocket.reset()
  vi.stubGlobal('WebSocket', MockWebSocket)
  // jsdom sets window.location.protocol = 'about:' which won't match 'https:'
  // — so WS_BASE will use the ws: branch
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

// ── helpers ────────────────────────────────────────────────────────────────────

function makeClient(onMessage = vi.fn(), onError = vi.fn()) {
  return new TaskNotificationClient('test-token', onMessage, onError)
}

// ── tests ──────────────────────────────────────────────────────────────────────

describe('TaskNotificationClient — connect', () => {
  test('creates a WebSocket with the token in the URL', () => {
    const client = makeClient()
    client.connect()

    expect(MockWebSocket.instances).toHaveLength(1)
    expect(MockWebSocket.instances[0].url).toContain('token=test-token')
  })

  test('WebSocket URL targets the ws/tasks endpoint', () => {
    const client = makeClient()
    client.connect()

    expect(MockWebSocket.instances[0].url).toMatch(/\/ws\/tasks/)
  })
})

describe('TaskNotificationClient — message handling', () => {
  test('calls onMessage with parsed JSON data', () => {
    const onMessage = vi.fn()
    const client = makeClient(onMessage)
    client.connect()

    const ws = MockWebSocket.instances[0]
    ws.onmessage({ data: JSON.stringify({ type: 'crawl_complete', payload: { id: 'a-1' } }) })

    expect(onMessage).toHaveBeenCalledOnce()
    expect(onMessage).toHaveBeenCalledWith({ type: 'crawl_complete', payload: { id: 'a-1' } })
  })

  test('ignores unparseable WebSocket frames without throwing', () => {
    const onMessage = vi.fn()
    const client = makeClient(onMessage)
    client.connect()

    const ws = MockWebSocket.instances[0]
    expect(() => ws.onmessage({ data: 'not json' })).not.toThrow()
    expect(onMessage).not.toHaveBeenCalled()
  })
})

describe('TaskNotificationClient — error handling', () => {
  test('calls onError when WebSocket fires an error', () => {
    const onError = vi.fn()
    const client = makeClient(vi.fn(), onError)
    client.connect()

    const ws = MockWebSocket.instances[0]
    const fakeErr = new Event('error')
    ws.onerror(fakeErr)

    expect(onError).toHaveBeenCalledWith(fakeErr)
  })

  test('does not throw when onError is not provided', () => {
    const client = new TaskNotificationClient('tok', vi.fn()) // no onError
    client.connect()

    const ws = MockWebSocket.instances[0]
    expect(() => ws.onerror(new Event('error'))).not.toThrow()
  })
})

describe('TaskNotificationClient — disconnect', () => {
  test('sets ws to null after disconnect', () => {
    const client = makeClient()
    client.connect()
    client.disconnect()

    expect(client.ws).toBeNull()
  })

  test('does not reconnect after intentional disconnect', () => {
    vi.useFakeTimers()
    const client = makeClient()
    client.connect()

    const ws = MockWebSocket.instances[0]
    client.disconnect()

    // The close handler fires *after* disconnect sets _intentionalClose = true
    // Trigger it manually to confirm no reconnect is scheduled
    ws.onclose?.()
    vi.advanceTimersByTime(5000)

    // Only the original WebSocket was created — no reconnect
    expect(MockWebSocket.instances).toHaveLength(1)
  })
})

describe('TaskNotificationClient — reconnect', () => {
  test('reconnects after unexpected close', () => {
    vi.useFakeTimers()
    const client = makeClient()
    client.connect()

    const ws = MockWebSocket.instances[0]
    // Simulate unexpected close (server dropped connection)
    ws.onclose?.()

    vi.advanceTimersByTime(3001)

    // A second WebSocket should have been created
    expect(MockWebSocket.instances).toHaveLength(2)
  })

  test('does not reconnect before 3 s delay', () => {
    vi.useFakeTimers()
    const client = makeClient()
    client.connect()

    MockWebSocket.instances[0].onclose?.()
    vi.advanceTimersByTime(2999)

    expect(MockWebSocket.instances).toHaveLength(1)
  })
})
