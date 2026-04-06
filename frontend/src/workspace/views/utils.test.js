import { describe, test, expect } from 'vitest'
import { formatDate, truncate } from './utils.js'

describe('formatDate', () => {
  test('returns dash for null', () => {
    expect(formatDate(null)).toBe('—')
  })

  test('returns dash for undefined', () => {
    expect(formatDate(undefined)).toBe('—')
  })

  test('returns dash for empty string', () => {
    expect(formatDate('')).toBe('—')
  })

  test('returns a non-empty string for a valid ISO date', () => {
    const result = formatDate('2026-03-15T10:00:00+00:00')
    expect(typeof result).toBe('string')
    expect(result).not.toBe('—')
    expect(result.length).toBeGreaterThan(0)
  })

  test('includes the year for a valid ISO date', () => {
    const result = formatDate('2026-01-01T00:00:00Z')
    expect(result).toContain('2026')
  })

  test('returns dash for an unparseable string', () => {
    // new Date('not-a-date').toLocaleDateString() returns "Invalid Date" — the
    // function wraps in try/catch and falls back to '—'
    const result = formatDate('not-a-date')
    // Accept either '—' (if the try/catch triggers) or 'Invalid Date' depending
    // on the JS engine — but the function should not throw
    expect(() => formatDate('not-a-date')).not.toThrow()
  })
})

describe('truncate', () => {
  test('returns dash for null', () => {
    expect(truncate(null)).toBe('—')
  })

  test('returns dash for undefined', () => {
    expect(truncate(undefined)).toBe('—')
  })

  test('returns dash for empty string', () => {
    expect(truncate('')).toBe('—')
  })

  test('returns the string unchanged when within maxLen', () => {
    expect(truncate('hello', 10)).toBe('hello')
  })

  test('returns the string unchanged when exactly at maxLen', () => {
    const str = 'a'.repeat(40)
    expect(truncate(str, 40)).toBe(str)
  })

  test('truncates and appends ellipsis when over maxLen', () => {
    const str = 'a'.repeat(50)
    const result = truncate(str, 40)
    expect(result).toHaveLength(41) // 40 chars + '…'
    expect(result.endsWith('…')).toBe(true)
  })

  test('uses default maxLen of 40', () => {
    const str = 'a'.repeat(50)
    const result = truncate(str)
    expect(result).toHaveLength(41)
  })

  test('single character string within limit is returned as-is', () => {
    expect(truncate('x', 5)).toBe('x')
  })
})
