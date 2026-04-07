import { describe, test, expect } from 'vitest'

import { formatError as formatApiErrorPayload } from './lib/api.js'
import { parseIcpJsonInput, validateIcpPayloadShape } from './icp-payload.js'

const validPayload = {
  name: 'US Mid-Market SaaS',
  priority: 1,
  fit_hypothesis: 'Strong conversion profile',
  geo: { countries: ['united states'], regions: [], metros: [], cities: [] },
  org: {
    employee_count: { min: 50, max: 500 },
    size_bands: ['51-200'],
    ownership_types: ['private'],
    has_website: true,
    has_linkedin: true,
  },
  industry_spec: {
    sectors: ['software'],
    subsectors: ['sales technology'],
    codes: { naics: ['511210'], sic: ['7372'] },
  },
  capability_spec: {
    offers: ['crm'],
    delivery_modes: ['saas'],
    customer_types: ['b2b'],
    domain_terms: ['revops'],
  },
  signal_spec: {
    exact: ['plg'],
    phrases: ['sales engagement'],
    broad: ['automation'],
  },
  exclusions: {
    countries: [],
    ownership_types: [],
    industries: ['staffing'],
    keywords: ['agency'],
    company_names: [],
  },
  adapter_hints: {},
  v: 1,
}

describe('parseIcpJsonInput', () => {
  test('throws SyntaxError on bad JSON', () => {
    expect(() => parseIcpJsonInput('{bad json')).toThrow(SyntaxError)
  })
})

describe('validateIcpPayloadShape', () => {
  test('valid payload passes', () => {
    const validResult = validateIcpPayloadShape(validPayload)
    expect(validResult.valid).toBe(true)
    expect(validResult.payload.name).toBe('US Mid-Market SaaS')
  })

  test('missing name fails', () => {
    const missingNameResult = validateIcpPayloadShape({ ...validPayload, name: '   ' })
    expect(missingNameResult.valid).toBe(false)
    expect(missingNameResult.errors.join('\n')).toMatch(/name is required/i)
  })

  test('wrong type for employee_count.min fails', () => {
    const nestedTypeResult = validateIcpPayloadShape({
      ...validPayload,
      org: {
        ...validPayload.org,
        employee_count: { min: '50', max: 500 },
      },
    })
    expect(nestedTypeResult.valid).toBe(false)
    expect(nestedTypeResult.errors.join('\n')).toMatch(/org\.employee_count\.min/i)
  })
})

describe('formatApiErrorPayload', () => {
  test('formats nested detail array correctly', () => {
    const message = formatApiErrorPayload({
      detail: [
        { loc: ['body', 'org', 'employee_count', 'min'], msg: 'Input should be a valid integer' },
        { loc: ['body', 'name'], msg: 'Field required' },
      ],
    })
    expect(message).toMatch(/org\.employee_count\.min: Input should be a valid integer/)
    expect(message).toMatch(/name: Field required/)
  })
})
