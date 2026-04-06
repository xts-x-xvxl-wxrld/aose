const ICP_BLOCK_KEYS = [
  'geo',
  'org',
  'industry_spec',
  'capability_spec',
  'signal_spec',
  'exclusions',
]

const listFieldPaths = [
  ['geo', 'countries'],
  ['geo', 'regions'],
  ['geo', 'metros'],
  ['geo', 'cities'],
  ['org', 'size_bands'],
  ['org', 'ownership_types'],
  ['industry_spec', 'sectors'],
  ['industry_spec', 'subsectors'],
  ['industry_spec', 'codes', 'naics'],
  ['industry_spec', 'codes', 'sic'],
  ['capability_spec', 'offers'],
  ['capability_spec', 'delivery_modes'],
  ['capability_spec', 'customer_types'],
  ['capability_spec', 'domain_terms'],
  ['signal_spec', 'exact'],
  ['signal_spec', 'phrases'],
  ['signal_spec', 'broad'],
  ['exclusions', 'countries'],
  ['exclusions', 'ownership_types'],
  ['exclusions', 'industries'],
  ['exclusions', 'keywords'],
  ['exclusions', 'company_names'],
]

function isPlainObject(value) {
  return Boolean(value) && !Array.isArray(value) && typeof value === 'object'
}

function readPath(target, path) {
  return path.reduce((value, key) => value?.[key], target)
}

function writePath(target, path, value) {
  let cursor = target
  for (let index = 0; index < path.length - 1; index += 1) {
    const key = path[index]
    if (!isPlainObject(cursor[key])) {
      cursor[key] = {}
    }
    cursor = cursor[key]
  }
  cursor[path[path.length - 1]] = value
}

function parseList(value) {
  const seen = new Set()
  return String(value || '')
    .split(',')
    .map((item) => item.trim().toLowerCase())
    .filter((item) => item && !seen.has(item) && seen.add(item))
}

export function formatList(value) {
  return Array.isArray(value) ? value.join(', ') : ''
}

export function emptyToNull(value) {
  return String(value || '').trim() ? String(value).trim() : null
}

export function parseIntOrNull(value) {
  const trimmed = String(value || '').trim()
  if (!trimmed) {
    return null
  }
  const parsed = Number.parseInt(trimmed, 10)
  return Number.isNaN(parsed) ? null : parsed
}

export function parseBooleanOrNull(value) {
  if (value === 'true') {
    return true
  }
  if (value === 'false') {
    return false
  }
  return null
}

export function formatBoolean(value) {
  if (value === true) {
    return 'true'
  }
  if (value === false) {
    return 'false'
  }
  return ''
}

export function parseJsonObject(value) {
  const trimmed = String(value || '').trim()
  if (!trimmed) {
    return {}
  }
  const parsed = JSON.parse(trimmed)
  if (!isPlainObject(parsed)) {
    throw new Error('Adapter hints must be a JSON object.')
  }
  return parsed
}

export function buildIcpPayloadFromForm(icpForm) {
  return {
    name: icpForm.name.trim(),
    priority: Number(icpForm.priority) || 1,
    fit_hypothesis: emptyToNull(icpForm.fit_hypothesis),
    geo: {
      countries: icpForm.geo.countries,
      regions: icpForm.geo.regions,
      metros: icpForm.geo.metros,
      cities: icpForm.geo.cities,
    },
    org: {
      employee_count: {
        min: icpForm.org.employee_count.min,
        max: icpForm.org.employee_count.max,
      },
      size_bands: icpForm.org.size_bands,
      ownership_types: icpForm.org.ownership_types,
      has_website: icpForm.org.has_website,
      has_linkedin: icpForm.org.has_linkedin,
    },
    industry_spec: {
      sectors: icpForm.industry.sectors,
      subsectors: icpForm.industry.subsectors,
      codes: {
        naics: icpForm.industry.codes.naics,
        sic: icpForm.industry.codes.sic,
      },
    },
    capability_spec: {
      offers: icpForm.capability.offers,
      delivery_modes: icpForm.capability.delivery_modes,
      customer_types: icpForm.capability.customer_types,
      domain_terms: icpForm.capability.domain_terms,
    },
    signal_spec: {
      exact: icpForm.signal.exact,
      phrases: icpForm.signal.phrases,
      broad: icpForm.signal.broad,
    },
    exclusions: {
      countries: icpForm.exclusions.countries,
      ownership_types: icpForm.exclusions.ownership_types,
      industries: icpForm.exclusions.industries,
      keywords: icpForm.exclusions.keywords,
      company_names: icpForm.exclusions.company_names,
    },
    adapter_hints: icpForm.adapter_hints,
    v: Number(icpForm.v) || 1,
  }
}

export function parseIcpJsonInput(rawValue) {
  const trimmed = String(rawValue || '').trim()
  if (!trimmed) {
    throw new Error('Paste a JSON object to import.')
  }

  const parsed = JSON.parse(trimmed)
  if (!isPlainObject(parsed)) {
    throw new Error('ICP import payload must be a top-level JSON object.')
  }
  return parsed
}

function normalizeStringField(payload, key, errors, label, { required = false } = {}) {
  const value = payload[key]
  if (value == null) {
    if (required) {
      errors.push(`${label} is required.`)
    }
    return
  }

  if (typeof value !== 'string') {
    errors.push(`${label} must be a string.`)
    return
  }

  const trimmed = value.trim()
  if (!trimmed) {
    if (required) {
      errors.push(`${label} is required.`)
    }
    return
  }

  payload[key] = trimmed
}

function normalizeIntegerField(payload, key, errors, label, { min = 0, max, defaultValue } = {}) {
  const value = payload[key]
  if (value == null) {
    if (defaultValue !== undefined) {
      payload[key] = defaultValue
    }
    return
  }

  if (!Number.isInteger(value) || value < min) {
    errors.push(`${label} must be an integer greater than or equal to ${min}.`)
    return
  }

  if (max !== undefined && value > max) {
    errors.push(`${label} must be an integer less than or equal to ${max}.`)
  }
}

function normalizeBooleanField(payload, key, errors, label) {
  const value = payload[key]
  if (value == null) {
    payload[key] = null
    return
  }

  if (typeof value !== 'boolean') {
    errors.push(`${label} must be true, false, or null.`)
  }
}

function normalizeIntegerOrNullField(payload, key, errors, label) {
  const value = payload[key]
  if (value == null) {
    payload[key] = null
    return
  }

  if (!Number.isInteger(value) || value < 0) {
    errors.push(`${label} must be a non-negative integer or null.`)
  }
}

function normalizeListField(payload, path, errors) {
  const label = path.join('.')
  const value = readPath(payload, path)
  if (value == null) {
    writePath(payload, path, [])
    return
  }

  if (!Array.isArray(value)) {
    errors.push(`${label} must be an array of strings.`)
    return
  }

  const normalized = []
  for (const item of value) {
    if (typeof item !== 'string' || !item.trim()) {
      errors.push(`${label} must contain only non-empty strings.`)
      return
    }
    if (!normalized.includes(item.trim())) {
      normalized.push(item.trim())
    }
  }

  writePath(payload, path, normalized)
}

export function validateIcpPayloadShape(inputPayload) {
  const payload = structuredClone(inputPayload)
  const errors = []

  if (!isPlainObject(payload)) {
    return {
      valid: false,
      errors: ['ICP payload must be a JSON object.'],
      payload: null,
    }
  }

  normalizeStringField(payload, 'name', errors, 'name', { required: true })
  normalizeIntegerField(payload, 'priority', errors, 'priority', { min: 1, max: 5, defaultValue: 1 })
  normalizeStringField(payload, 'fit_hypothesis', errors, 'fit_hypothesis')
  if (payload.fit_hypothesis == null || payload.fit_hypothesis === '') {
    payload.fit_hypothesis = null
  }
  normalizeIntegerField(payload, 'v', errors, 'v', { min: 1, defaultValue: 1 })

  for (const key of ICP_BLOCK_KEYS) {
    if (payload[key] == null) {
      payload[key] = {}
      continue
    }
    if (!isPlainObject(payload[key])) {
      errors.push(`${key} must be an object.`)
    }
  }

  if (payload.adapter_hints == null) {
    payload.adapter_hints = {}
  } else if (!isPlainObject(payload.adapter_hints)) {
    errors.push('adapter_hints must be an object.')
  }

  listFieldPaths.forEach((path) => normalizeListField(payload, path, errors))

  const employeeCount = isPlainObject(payload.org?.employee_count) ? payload.org.employee_count : {}
  payload.org.employee_count = employeeCount
  normalizeIntegerOrNullField(employeeCount, 'min', errors, 'org.employee_count.min')
  normalizeIntegerOrNullField(employeeCount, 'max', errors, 'org.employee_count.max')
  if (
    Number.isInteger(employeeCount.min) &&
    Number.isInteger(employeeCount.max) &&
    employeeCount.min > employeeCount.max
  ) {
    errors.push('org.employee_count.min must be less than or equal to org.employee_count.max.')
  }

  normalizeBooleanField(payload.org, 'has_website', errors, 'org.has_website')
  normalizeBooleanField(payload.org, 'has_linkedin', errors, 'org.has_linkedin')

  return {
    valid: errors.length === 0,
    errors,
    payload: errors.length === 0 ? payload : null,
  }
}
