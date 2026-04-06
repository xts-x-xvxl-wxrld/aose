import React, { useCallback, useContext, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { listIcps, createIcp, updateIcp } from '../api.js'
import {
  buildIcpPayloadFromForm,
  formatBoolean as formatBooleanValue,
  parseIcpJsonInput,
  parseBooleanOrNull,
  parseIntOrNull,
  validateIcpPayloadShape,
} from '../icp-payload.js'
import { AuthContext } from '../App.jsx'

const SIZE_BANDS = ['1-10', '11-50', '51-200', '201-500', '501-1000', '1001-5000', '5001-10000', '10001+']
const OWNERSHIP_TYPES = ['educational', 'government', 'nonprofit', 'private', 'public', 'public_subsidiary']
const PRIORITY_OPTIONS = [1, 2, 3, 4, 5]

function defaultIcpForm() {
  return {
    id: '',
    name: '',
    priority: 1,
    fit_hypothesis: '',
    geo: {
      countries: [''],
      regions: [''],
      metros: [''],
      cities: [''],
    },
    org: {
      employee_count: { min: '', max: '' },
      size_bands: [],
      ownership_types: [],
      has_website: '',
      has_linkedin: '',
    },
    industry: {
      sectors: [''],
      subsectors: [''],
      codes: { naics: [''], sic: [''] },
    },
    capability: {
      offers: [''],
      delivery_modes: [''],
      customer_types: [''],
      domain_terms: [''],
    },
    signal: {
      exact: [''],
      phrases: [''],
      broad: [''],
    },
    exclusions: {
      countries: [''],
      ownership_types: [],
      industries: [''],
      keywords: [''],
      company_names: [''],
    },
    adapter_hints: {
      pdl: {
        use_employee_count_over_size: false,
        industry_field_preference: '',
        require_industry_or_signal_match: false,
        signal_minimum_should_match: '1',
      },
    },
    v: 1,
  }
}

function loadIcpIntoForm(icp) {
  if (!icp) return defaultIcpForm()
  return {
    id: icp.id,
    name: icp.name || '',
    priority: icp.priority ?? 1,
    fit_hypothesis: icp.fit_hypothesis || '',
    geo: {
      countries: Array.isArray(icp.geo?.countries) && icp.geo.countries.length ? [...icp.geo.countries] : [''],
      regions: Array.isArray(icp.geo?.regions) && icp.geo.regions.length ? [...icp.geo.regions] : [''],
      metros: Array.isArray(icp.geo?.metros) && icp.geo.metros.length ? [...icp.geo.metros] : [''],
      cities: Array.isArray(icp.geo?.cities) && icp.geo.cities.length ? [...icp.geo.cities] : [''],
    },
    org: {
      employee_count: {
        min: icp.org?.employee_count?.min ?? '',
        max: icp.org?.employee_count?.max ?? '',
      },
      size_bands: [...(icp.org?.size_bands || [])],
      ownership_types: [...(icp.org?.ownership_types || [])],
      has_website: formatBooleanValue(icp.org?.has_website),
      has_linkedin: formatBooleanValue(icp.org?.has_linkedin),
    },
    industry: {
      sectors: Array.isArray(icp.industry_spec?.sectors) && icp.industry_spec.sectors.length ? [...icp.industry_spec.sectors] : [''],
      subsectors: Array.isArray(icp.industry_spec?.subsectors) && icp.industry_spec.subsectors.length ? [...icp.industry_spec.subsectors] : [''],
      codes: {
        naics: Array.isArray(icp.industry_spec?.codes?.naics) && icp.industry_spec.codes.naics.length ? [...icp.industry_spec.codes.naics] : [''],
        sic: Array.isArray(icp.industry_spec?.codes?.sic) && icp.industry_spec.codes.sic.length ? [...icp.industry_spec.codes.sic] : [''],
      },
    },
    capability: {
      offers: Array.isArray(icp.capability_spec?.offers) && icp.capability_spec.offers.length ? [...icp.capability_spec.offers] : [''],
      delivery_modes: Array.isArray(icp.capability_spec?.delivery_modes) && icp.capability_spec.delivery_modes.length ? [...icp.capability_spec.delivery_modes] : [''],
      customer_types: Array.isArray(icp.capability_spec?.customer_types) && icp.capability_spec.customer_types.length ? [...icp.capability_spec.customer_types] : [''],
      domain_terms: Array.isArray(icp.capability_spec?.domain_terms) && icp.capability_spec.domain_terms.length ? [...icp.capability_spec.domain_terms] : [''],
    },
    signal: {
      exact: Array.isArray(icp.signal_spec?.exact) && icp.signal_spec.exact.length ? [...icp.signal_spec.exact] : [''],
      phrases: Array.isArray(icp.signal_spec?.phrases) && icp.signal_spec.phrases.length ? [...icp.signal_spec.phrases] : [''],
      broad: Array.isArray(icp.signal_spec?.broad) && icp.signal_spec.broad.length ? [...icp.signal_spec.broad] : [''],
    },
    exclusions: {
      countries: Array.isArray(icp.exclusions?.countries) && icp.exclusions.countries.length ? [...icp.exclusions.countries] : [''],
      ownership_types: [...(icp.exclusions?.ownership_types || [])],
      industries: Array.isArray(icp.exclusions?.industries) && icp.exclusions.industries.length ? [...icp.exclusions.industries] : [''],
      keywords: Array.isArray(icp.exclusions?.keywords) && icp.exclusions.keywords.length ? [...icp.exclusions.keywords] : [''],
      company_names: Array.isArray(icp.exclusions?.company_names) && icp.exclusions.company_names.length ? [...icp.exclusions.company_names] : [''],
    },
    adapter_hints: {
      pdl: {
        use_employee_count_over_size: Boolean(icp.adapter_hints?.pdl?.use_employee_count_over_size),
        industry_field_preference: icp.adapter_hints?.pdl?.industry_field_preference || '',
        require_industry_or_signal_match: Boolean(icp.adapter_hints?.pdl?.require_industry_or_signal_match),
        signal_minimum_should_match: String(icp.adapter_hints?.pdl?.signal_minimum_should_match ?? 1),
      },
    },
    v: icp.v ?? 1,
  }
}

function normalizeTextRows(values, { preserveCase = false } = {}) {
  const seen = new Set()
  const normalized = []
  for (const value of values) {
    const trimmed = String(value || '').trim()
    if (!trimmed) continue
    const finalValue = preserveCase ? trimmed : trimmed.toLowerCase()
    if (!seen.has(finalValue)) {
      seen.add(finalValue)
      normalized.push(finalValue)
    }
  }
  return normalized
}

function normalizeCodeRows(values, { minLength, maxLength }) {
  const normalized = normalizeTextRows(values, { preserveCase: true })
  const invalid = normalized.filter((value) => !new RegExp(`^\\d{${minLength},${maxLength}}$`).test(value))
  if (invalid.length) {
    throw new Error(`Codes must be numeric. Invalid values: ${invalid.join(', ')}`)
  }
  return normalized
}

function normalizeIcpForm(form) {
  return {
    name: form.name.trim(),
    priority: Number(form.priority) || 1,
    fit_hypothesis: form.fit_hypothesis,
    geo: {
      countries: normalizeTextRows(form.geo.countries),
      regions: normalizeTextRows(form.geo.regions),
      metros: normalizeTextRows(form.geo.metros),
      cities: normalizeTextRows(form.geo.cities),
    },
    org: {
      employee_count: {
        min: parseIntOrNull(form.org.employee_count.min),
        max: parseIntOrNull(form.org.employee_count.max),
      },
      size_bands: [...form.org.size_bands],
      ownership_types: [...form.org.ownership_types],
      has_website: parseBooleanOrNull(form.org.has_website),
      has_linkedin: parseBooleanOrNull(form.org.has_linkedin),
    },
    industry: {
      sectors: normalizeTextRows(form.industry.sectors),
      subsectors: normalizeTextRows(form.industry.subsectors),
      codes: {
        naics: normalizeCodeRows(form.industry.codes.naics, { minLength: 2, maxLength: 6 }),
        sic: normalizeCodeRows(form.industry.codes.sic, { minLength: 4, maxLength: 4 }),
      },
    },
    capability: {
      offers: normalizeTextRows(form.capability.offers),
      delivery_modes: normalizeTextRows(form.capability.delivery_modes),
      customer_types: normalizeTextRows(form.capability.customer_types),
      domain_terms: normalizeTextRows(form.capability.domain_terms),
    },
    signal: {
      exact: normalizeTextRows(form.signal.exact),
      phrases: normalizeTextRows(form.signal.phrases),
      broad: normalizeTextRows(form.signal.broad),
    },
    exclusions: {
      countries: normalizeTextRows(form.exclusions.countries),
      ownership_types: [...form.exclusions.ownership_types],
      industries: normalizeTextRows(form.exclusions.industries),
      keywords: normalizeTextRows(form.exclusions.keywords),
      company_names: normalizeTextRows(form.exclusions.company_names),
    },
    adapter_hints: {
      pdl: {
        use_employee_count_over_size: Boolean(form.adapter_hints.pdl.use_employee_count_over_size),
        industry_field_preference: form.adapter_hints.pdl.industry_field_preference || null,
        require_industry_or_signal_match: Boolean(form.adapter_hints.pdl.require_industry_or_signal_match),
        signal_minimum_should_match: Number(form.adapter_hints.pdl.signal_minimum_should_match) || 1,
      },
    },
    v: Number(form.v) || 1,
  }
}

function hasMeaningfulRows(values) {
  return values.some((value) => String(value || '').trim())
}

// RepeatableList component for flat arrays
function RepeatableList({ label, values, onChange, placeholder }) {
  function handleChange(index, value) {
    const next = [...values]
    next[index] = value
    onChange(next)
  }

  function handleRemove(index) {
    if (values.length === 1) {
      onChange([''])
      return
    }
    onChange(values.filter((_, i) => i !== index))
  }

  function handleAdd() {
    onChange([...values, ''])
  }

  return (
    <div>
      <span>{label}</span>
      {values.map((value, index) => (
        <div key={index} className="repeatable-row">
          <input
            type="text"
            placeholder={placeholder}
            value={value}
            onChange={(e) => handleChange(index, e.target.value)}
          />
          <button className="ghost" type="button" onClick={() => handleRemove(index)}>
            Remove
          </button>
        </div>
      ))}
      <button className="ghost add-row-button" type="button" onClick={handleAdd}>
        + Add {label.toLowerCase()}
      </button>
    </div>
  )
}

export default function ICPEditorPage() {
  const { token } = useContext(AuthContext)
  const { sellerId, icpId } = useParams()
  const navigate = useNavigate()

  const isEditing = Boolean(icpId)

  const [form, setForm] = useState(defaultIcpForm)
  const [icpCreateMode, setIcpCreateMode] = useState('manual')
  const [icpJsonInput, setIcpJsonInput] = useState('')
  const [icpJsonErrors, setIcpJsonErrors] = useState([])
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [loadingIcp, setLoadingIcp] = useState(false)

  useEffect(() => {
    if (!token || !sellerId) return
    if (!isEditing) {
      setForm(defaultIcpForm())
      setIcpCreateMode('manual')
      setIcpJsonInput('')
      setIcpJsonErrors([])
      return
    }
    setLoadingIcp(true)
    listIcps(token, sellerId)
      .then((data) => {
        const matched = data.find((icp) => icp.id === icpId)
        if (matched) {
          setForm(loadIcpIntoForm(matched))
          setIcpCreateMode('manual')
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoadingIcp(false))
  }, [token, sellerId, icpId, isEditing])

  // Computed warnings
  const sizeWithoutEmployeeCountWarning =
    form.org.size_bands.length > 0 &&
    !String(form.org.employee_count.min || '').trim() &&
    !String(form.org.employee_count.max || '').trim()

  const looseQueryWarning = (() => {
    const hardFilters =
      hasMeaningfulRows(form.geo.countries) ||
      hasMeaningfulRows(form.geo.regions) ||
      hasMeaningfulRows(form.geo.metros) ||
      hasMeaningfulRows(form.geo.cities) ||
      Boolean(String(form.org.employee_count.min || '').trim()) ||
      Boolean(String(form.org.employee_count.max || '').trim()) ||
      form.org.size_bands.length > 0 ||
      form.org.ownership_types.length > 0 ||
      form.org.has_website !== '' ||
      form.org.has_linkedin !== '' ||
      hasMeaningfulRows(form.industry.sectors) ||
      hasMeaningfulRows(form.industry.subsectors) ||
      hasMeaningfulRows(form.industry.codes.naics) ||
      hasMeaningfulRows(form.industry.codes.sic)
    const hasBroad = hasMeaningfulRows(form.signal.broad)
    const hasOtherEvidence =
      hasMeaningfulRows(form.signal.exact) ||
      hasMeaningfulRows(form.signal.phrases) ||
      hasMeaningfulRows(form.capability.domain_terms)
    return hasBroad && !hasOtherEvidence && !hardFilters
  })()

  const canSave = Boolean(sellerId && form.name.trim())
  const canImport = Boolean(sellerId && icpJsonInput.trim())

  // Setters using immutable updates

  function setField(path, value) {
    setForm((prev) => {
      const next = structuredClone(prev)
      let cursor = next
      for (let i = 0; i < path.length - 1; i++) {
        cursor = cursor[path[i]]
      }
      cursor[path[path.length - 1]] = value
      return next
    })
  }

  function setRepeatableValue(section, field, index, value) {
    setForm((prev) => {
      const next = structuredClone(prev)
      next[section][field][index] = value
      return next
    })
  }

  function addRepeatableValue(section, field) {
    setForm((prev) => {
      const next = structuredClone(prev)
      next[section][field].push('')
      return next
    })
  }

  function removeRepeatableValue(section, field, index) {
    setForm((prev) => {
      const next = structuredClone(prev)
      if (next[section][field].length === 1) {
        next[section][field][0] = ''
      } else {
        next[section][field].splice(index, 1)
      }
      return next
    })
  }

  function setNestedRepeatableValue(section, parentField, field, index, value) {
    setForm((prev) => {
      const next = structuredClone(prev)
      next[section][parentField][field][index] = value
      return next
    })
  }

  function addNestedRepeatableValue(section, parentField, field) {
    setForm((prev) => {
      const next = structuredClone(prev)
      next[section][parentField][field].push('')
      return next
    })
  }

  function removeNestedRepeatableValue(section, parentField, field, index) {
    setForm((prev) => {
      const next = structuredClone(prev)
      if (next[section][parentField][field].length === 1) {
        next[section][parentField][field][0] = ''
      } else {
        next[section][parentField][field].splice(index, 1)
      }
      return next
    })
  }

  function toggleFixedChoice(section, field, value) {
    setForm((prev) => {
      const next = structuredClone(prev)
      const arr = next[section][field]
      const idx = arr.indexOf(value)
      if (idx >= 0) {
        arr.splice(idx, 1)
      } else {
        arr.push(value)
      }
      return next
    })
  }

  async function handleSave(e) {
    e.preventDefault()
    if (!canSave) return
    setSaving(true)
    setMessage('')
    setError('')
    try {
      const payload = buildIcpPayloadFromForm(normalizeIcpForm(form))
      const validation = validateIcpPayloadShape(payload)
      if (!validation.valid) {
        setError(validation.errors.join(' '))
        return
      }
      if (form.id) {
        await updateIcp(token, sellerId, form.id, validation.payload)
        setMessage('ICP updated.')
      } else {
        await createIcp(token, sellerId, validation.payload)
        setMessage('ICP created.')
      }
      navigate(`/sellers/${sellerId}/icps`)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleImportJson(e) {
    e.preventDefault()
    if (!canImport) return
    setSaving(true)
    setMessage('')
    setError('')
    setIcpJsonErrors([])
    try {
      const parsed = parseIcpJsonInput(icpJsonInput)
      const validation = validateIcpPayloadShape(parsed)
      if (!validation.valid) {
        setIcpJsonErrors(validation.errors)
        return
      }
      await createIcp(token, sellerId, validation.payload)
      setIcpJsonInput('')
      setIcpCreateMode('manual')
      setMessage('ICP imported.')
      navigate(`/sellers/${sellerId}/icps`)
    } catch (err) {
      const lines = String(err.message || 'Import failed.')
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
      setIcpJsonErrors(lines.length ? lines : ['Import failed.'])
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (!sellerId) {
    return (
      <div className="page-stack">
        <section className="panel">
          <p className="empty">Select a seller before editing ICPs.</p>
        </section>
      </div>
    )
  }

  if (loadingIcp) {
    return (
      <div className="page-stack">
        <section className="panel">
          <p className="empty">Loading ICP...</p>
        </section>
      </div>
    )
  }

  return (
    <div className="page-stack">
      {message && <p className="notice success">{message}</p>}
      {error && <p className="notice error">{error}</p>}

      <section className="panel">
        <div className="panel-heading">
          <h2>{form.id ? 'Edit ICP' : 'Create ICP'}</h2>
          <button className="ghost" type="button" onClick={() => navigate(`/sellers/${sellerId}/icps`)}>
            Back to ICP dashboard
          </button>
        </div>

        <div className="stack">
          {!form.id && (
            <div className="mode-switch">
              <button
                className={`ghost${icpCreateMode === 'manual' ? ' active' : ''}`}
                type="button"
                onClick={() => setIcpCreateMode('manual')}
              >
                Manual
              </button>
              <button
                className={`ghost${icpCreateMode === 'json' ? ' active' : ''}`}
                type="button"
                onClick={() => setIcpCreateMode('json')}
              >
                Paste ICP JSON
              </button>
            </div>
          )}

          {(form.id || icpCreateMode === 'manual') && (
            <form className="stack" onSubmit={handleSave}>
              <div className="form-grid">
                <label>
                  <span>Name</span>
                  <input
                    type="text"
                    placeholder="US mid-market SaaS"
                    value={form.name}
                    onChange={(e) => setField(['name'], e.target.value)}
                  />
                </label>
                <label>
                  <span>Priority</span>
                  <select
                    value={form.priority}
                    onChange={(e) => setField(['priority'], Number(e.target.value))}
                  >
                    {PRIORITY_OPTIONS.map((opt) => (
                      <option key={opt} value={opt}>Priority {opt}</option>
                    ))}
                  </select>
                </label>
                <label className="full">
                  <span>Fit hypothesis</span>
                  <textarea
                    rows={3}
                    placeholder="Why this segment should convert well."
                    value={form.fit_hypothesis}
                    onChange={(e) => setField(['fit_hypothesis'], e.target.value)}
                  />
                </label>
                <label>
                  <span>Version</span>
                  <input
                    type="number"
                    min="1"
                    value={form.v}
                    onChange={(e) => setField(['v'], e.target.value)}
                  />
                </label>
              </div>

              {/* Geography */}
              <section className="spec-section">
                <h3>Geography</h3>
                <div className="form-grid single-column">
                  <div>
                    <span>Countries</span>
                    {form.geo.countries.map((value, index) => (
                      <div key={`country-${index}`} className="repeatable-row">
                        <input
                          type="text"
                          placeholder="united states"
                          value={value}
                          onChange={(e) => setRepeatableValue('geo', 'countries', index, e.target.value)}
                        />
                        <button className="ghost" type="button" onClick={() => removeRepeatableValue('geo', 'countries', index)}>Remove</button>
                      </div>
                    ))}
                    <button className="ghost add-row-button" type="button" onClick={() => addRepeatableValue('geo', 'countries')}>Add country</button>
                  </div>
                  <div>
                    <span>Regions</span>
                    {form.geo.regions.map((value, index) => (
                      <div key={`region-${index}`} className="repeatable-row">
                        <input
                          type="text"
                          placeholder="california"
                          value={value}
                          onChange={(e) => setRepeatableValue('geo', 'regions', index, e.target.value)}
                        />
                        <button className="ghost" type="button" onClick={() => removeRepeatableValue('geo', 'regions', index)}>Remove</button>
                      </div>
                    ))}
                    <button className="ghost add-row-button" type="button" onClick={() => addRepeatableValue('geo', 'regions')}>Add region</button>
                  </div>
                  <div>
                    <span>Metros</span>
                    {form.geo.metros.map((value, index) => (
                      <div key={`metro-${index}`} className="repeatable-row">
                        <input
                          type="text"
                          placeholder="bay area"
                          value={value}
                          onChange={(e) => setRepeatableValue('geo', 'metros', index, e.target.value)}
                        />
                        <button className="ghost" type="button" onClick={() => removeRepeatableValue('geo', 'metros', index)}>Remove</button>
                      </div>
                    ))}
                    <button className="ghost add-row-button" type="button" onClick={() => addRepeatableValue('geo', 'metros')}>Add metro</button>
                  </div>
                  <div>
                    <span>Cities</span>
                    {form.geo.cities.map((value, index) => (
                      <div key={`city-${index}`} className="repeatable-row">
                        <input
                          type="text"
                          placeholder="san francisco"
                          value={value}
                          onChange={(e) => setRepeatableValue('geo', 'cities', index, e.target.value)}
                        />
                        <button className="ghost" type="button" onClick={() => removeRepeatableValue('geo', 'cities', index)}>Remove</button>
                      </div>
                    ))}
                    <button className="ghost add-row-button" type="button" onClick={() => addRepeatableValue('geo', 'cities')}>Add city</button>
                  </div>
                </div>
              </section>

              {/* Organization */}
              <section className="spec-section">
                <h3>Organization</h3>
                <div className="form-grid">
                  <label>
                    <span>Employee count min</span>
                    <input
                      type="number"
                      min="0"
                      placeholder="50"
                      value={form.org.employee_count.min}
                      onChange={(e) => setField(['org', 'employee_count', 'min'], e.target.value)}
                    />
                  </label>
                  <label>
                    <span>Employee count max</span>
                    <input
                      type="number"
                      min="0"
                      placeholder="500"
                      value={form.org.employee_count.max}
                      onChange={(e) => setField(['org', 'employee_count', 'max'], e.target.value)}
                    />
                  </label>
                  <label>
                    <span>Has website</span>
                    <select
                      value={form.org.has_website}
                      onChange={(e) => setField(['org', 'has_website'], e.target.value)}
                    >
                      <option value="">Any</option>
                      <option value="true">Required</option>
                      <option value="false">Must not have</option>
                    </select>
                  </label>
                  <label>
                    <span>Has LinkedIn</span>
                    <select
                      value={form.org.has_linkedin}
                      onChange={(e) => setField(['org', 'has_linkedin'], e.target.value)}
                    >
                      <option value="">Any</option>
                      <option value="true">Required</option>
                      <option value="false">Must not have</option>
                    </select>
                  </label>
                  <div className="full">
                    <span>Size bands</span>
                    <div className="chip-grid">
                      {SIZE_BANDS.map((option) => (
                        <label key={option} className="chip-option">
                          <input
                            type="checkbox"
                            checked={form.org.size_bands.includes(option)}
                            onChange={() => toggleFixedChoice('org', 'size_bands', option)}
                          />
                          <span>{option}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                  <div className="full">
                    <span>Ownership types</span>
                    <div className="chip-grid">
                      {OWNERSHIP_TYPES.map((option) => (
                        <label key={option} className="chip-option">
                          <input
                            type="checkbox"
                            checked={form.org.ownership_types.includes(option)}
                            onChange={() => toggleFixedChoice('org', 'ownership_types', option)}
                          />
                          <span>{option}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              </section>

              {/* Industry */}
              <section className="spec-section">
                <h3>Industry</h3>
                <div className="form-grid single-column">
                  <div>
                    <span>Sectors</span>
                    {form.industry.sectors.map((value, index) => (
                      <div key={`sector-${index}`} className="repeatable-row">
                        <input
                          type="text"
                          placeholder="software"
                          value={value}
                          onChange={(e) => setRepeatableValue('industry', 'sectors', index, e.target.value)}
                        />
                        <button className="ghost" type="button" onClick={() => removeRepeatableValue('industry', 'sectors', index)}>Remove</button>
                      </div>
                    ))}
                    <button className="ghost add-row-button" type="button" onClick={() => addRepeatableValue('industry', 'sectors')}>Add sector</button>
                  </div>
                  <div>
                    <span>Subsectors</span>
                    {form.industry.subsectors.map((value, index) => (
                      <div key={`subsector-${index}`} className="repeatable-row">
                        <input
                          type="text"
                          placeholder="sales software"
                          value={value}
                          onChange={(e) => setRepeatableValue('industry', 'subsectors', index, e.target.value)}
                        />
                        <button className="ghost" type="button" onClick={() => removeRepeatableValue('industry', 'subsectors', index)}>Remove</button>
                      </div>
                    ))}
                    <button className="ghost add-row-button" type="button" onClick={() => addRepeatableValue('industry', 'subsectors')}>Add subsector</button>
                  </div>
                  <div className="form-grid">
                    <div>
                      <span>NAICS codes</span>
                      {form.industry.codes.naics.map((value, index) => (
                        <div key={`naics-${index}`} className="repeatable-row">
                          <input
                            type="text"
                            placeholder="511210"
                            value={value}
                            onChange={(e) => setNestedRepeatableValue('industry', 'codes', 'naics', index, e.target.value)}
                          />
                          <button className="ghost" type="button" onClick={() => removeNestedRepeatableValue('industry', 'codes', 'naics', index)}>Remove</button>
                        </div>
                      ))}
                      <button className="ghost add-row-button" type="button" onClick={() => addNestedRepeatableValue('industry', 'codes', 'naics')}>Add NAICS code</button>
                    </div>
                    <div>
                      <span>SIC codes</span>
                      {form.industry.codes.sic.map((value, index) => (
                        <div key={`sic-${index}`} className="repeatable-row">
                          <input
                            type="text"
                            placeholder="7372"
                            value={value}
                            onChange={(e) => setNestedRepeatableValue('industry', 'codes', 'sic', index, e.target.value)}
                          />
                          <button className="ghost" type="button" onClick={() => removeNestedRepeatableValue('industry', 'codes', 'sic', index)}>Remove</button>
                        </div>
                      ))}
                      <button className="ghost add-row-button" type="button" onClick={() => addNestedRepeatableValue('industry', 'codes', 'sic')}>Add SIC code</button>
                    </div>
                  </div>
                </div>
              </section>

              {/* Capabilities */}
              <section className="spec-section">
                <h3>Capabilities</h3>
                <div className="form-grid single-column">
                  <div>
                    <span>Offers</span>
                    {form.capability.offers.map((value, index) => (
                      <div key={`offer-${index}`} className="repeatable-row">
                        <input
                          type="text"
                          placeholder="sales engagement"
                          value={value}
                          onChange={(e) => setRepeatableValue('capability', 'offers', index, e.target.value)}
                        />
                        <button className="ghost" type="button" onClick={() => removeRepeatableValue('capability', 'offers', index)}>Remove</button>
                      </div>
                    ))}
                    <button className="ghost add-row-button" type="button" onClick={() => addRepeatableValue('capability', 'offers')}>Add offer</button>
                  </div>
                  <div>
                    <span>Delivery modes</span>
                    {form.capability.delivery_modes.map((value, index) => (
                      <div key={`delivery-${index}`} className="repeatable-row">
                        <input
                          type="text"
                          placeholder="self-serve"
                          value={value}
                          onChange={(e) => setRepeatableValue('capability', 'delivery_modes', index, e.target.value)}
                        />
                        <button className="ghost" type="button" onClick={() => removeRepeatableValue('capability', 'delivery_modes', index)}>Remove</button>
                      </div>
                    ))}
                    <button className="ghost add-row-button" type="button" onClick={() => addRepeatableValue('capability', 'delivery_modes')}>Add delivery mode</button>
                  </div>
                  <div>
                    <span>Customer types</span>
                    {form.capability.customer_types.map((value, index) => (
                      <div key={`customer-${index}`} className="repeatable-row">
                        <input
                          type="text"
                          placeholder="revops team"
                          value={value}
                          onChange={(e) => setRepeatableValue('capability', 'customer_types', index, e.target.value)}
                        />
                        <button className="ghost" type="button" onClick={() => removeRepeatableValue('capability', 'customer_types', index)}>Remove</button>
                      </div>
                    ))}
                    <button className="ghost add-row-button" type="button" onClick={() => addRepeatableValue('capability', 'customer_types')}>Add customer type</button>
                  </div>
                  <div>
                    <span>Domain terms</span>
                    {form.capability.domain_terms.map((value, index) => (
                      <div key={`domain-${index}`} className="repeatable-row">
                        <input
                          type="text"
                          placeholder="outbound automation"
                          value={value}
                          onChange={(e) => setRepeatableValue('capability', 'domain_terms', index, e.target.value)}
                        />
                        <button className="ghost" type="button" onClick={() => removeRepeatableValue('capability', 'domain_terms', index)}>Remove</button>
                      </div>
                    ))}
                    <button className="ghost add-row-button" type="button" onClick={() => addRepeatableValue('capability', 'domain_terms')}>Add domain term</button>
                  </div>
                </div>
              </section>

              {/* Signals */}
              <section className="spec-section">
                <h3>Signals</h3>
                <div className="form-grid single-column">
                  <div>
                    <span>Exact</span>
                    {form.signal.exact.map((value, index) => (
                      <div key={`exact-${index}`} className="repeatable-row">
                        <input
                          type="text"
                          placeholder="sales engagement platform"
                          value={value}
                          onChange={(e) => setRepeatableValue('signal', 'exact', index, e.target.value)}
                        />
                        <button className="ghost" type="button" onClick={() => removeRepeatableValue('signal', 'exact', index)}>Remove</button>
                      </div>
                    ))}
                    <button className="ghost add-row-button" type="button" onClick={() => addRepeatableValue('signal', 'exact')}>Add exact signal</button>
                  </div>
                  <div>
                    <span>Phrases</span>
                    {form.signal.phrases.map((value, index) => (
                      <div key={`phrase-${index}`} className="repeatable-row">
                        <input
                          type="text"
                          placeholder="revenue operations"
                          value={value}
                          onChange={(e) => setRepeatableValue('signal', 'phrases', index, e.target.value)}
                        />
                        <button className="ghost" type="button" onClick={() => removeRepeatableValue('signal', 'phrases', index)}>Remove</button>
                      </div>
                    ))}
                    <button className="ghost add-row-button" type="button" onClick={() => addRepeatableValue('signal', 'phrases')}>Add phrase</button>
                  </div>
                  <div>
                    <span>Broad</span>
                    {form.signal.broad.map((value, index) => (
                      <div key={`broad-${index}`} className="repeatable-row">
                        <input
                          type="text"
                          placeholder="outbound sales"
                          value={value}
                          onChange={(e) => setRepeatableValue('signal', 'broad', index, e.target.value)}
                        />
                        <button className="ghost" type="button" onClick={() => removeRepeatableValue('signal', 'broad', index)}>Remove</button>
                      </div>
                    ))}
                    <button className="ghost add-row-button" type="button" onClick={() => addRepeatableValue('signal', 'broad')}>Add broad signal</button>
                  </div>
                </div>
              </section>

              {/* Exclusions */}
              <section className="spec-section">
                <h3>Exclusions</h3>
                <div className="form-grid single-column">
                  <div>
                    <span>Excluded countries</span>
                    {form.exclusions.countries.map((value, index) => (
                      <div key={`excl-country-${index}`} className="repeatable-row">
                        <input
                          type="text"
                          placeholder="russia"
                          value={value}
                          onChange={(e) => setRepeatableValue('exclusions', 'countries', index, e.target.value)}
                        />
                        <button className="ghost" type="button" onClick={() => removeRepeatableValue('exclusions', 'countries', index)}>Remove</button>
                      </div>
                    ))}
                    <button className="ghost add-row-button" type="button" onClick={() => addRepeatableValue('exclusions', 'countries')}>Add excluded country</button>
                  </div>
                  <div>
                    <span>Excluded ownership types</span>
                    <div className="chip-grid">
                      {OWNERSHIP_TYPES.map((option) => (
                        <label key={`exclude-${option}`} className="chip-option">
                          <input
                            type="checkbox"
                            checked={form.exclusions.ownership_types.includes(option)}
                            onChange={() => toggleFixedChoice('exclusions', 'ownership_types', option)}
                          />
                          <span>{option}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                  <div>
                    <span>Excluded industries</span>
                    {form.exclusions.industries.map((value, index) => (
                      <div key={`excl-industry-${index}`} className="repeatable-row">
                        <input
                          type="text"
                          placeholder="staffing and recruiting"
                          value={value}
                          onChange={(e) => setRepeatableValue('exclusions', 'industries', index, e.target.value)}
                        />
                        <button className="ghost" type="button" onClick={() => removeRepeatableValue('exclusions', 'industries', index)}>Remove</button>
                      </div>
                    ))}
                    <button className="ghost add-row-button" type="button" onClick={() => addRepeatableValue('exclusions', 'industries')}>Add excluded industry</button>
                  </div>
                  <div>
                    <span>Exclusion keywords</span>
                    {form.exclusions.keywords.map((value, index) => (
                      <div key={`excl-keyword-${index}`} className="repeatable-row">
                        <input
                          type="text"
                          placeholder="agency"
                          value={value}
                          onChange={(e) => setRepeatableValue('exclusions', 'keywords', index, e.target.value)}
                        />
                        <button className="ghost" type="button" onClick={() => removeRepeatableValue('exclusions', 'keywords', index)}>Remove</button>
                      </div>
                    ))}
                    <button className="ghost add-row-button" type="button" onClick={() => addRepeatableValue('exclusions', 'keywords')}>Add exclusion keyword</button>
                  </div>
                  <div>
                    <span>Excluded company names</span>
                    {form.exclusions.company_names.map((value, index) => (
                      <div key={`excl-company-${index}`} className="repeatable-row">
                        <input
                          type="text"
                          placeholder="acme consulting"
                          value={value}
                          onChange={(e) => setRepeatableValue('exclusions', 'company_names', index, e.target.value)}
                        />
                        <button className="ghost" type="button" onClick={() => removeRepeatableValue('exclusions', 'company_names', index)}>Remove</button>
                      </div>
                    ))}
                    <button className="ghost add-row-button" type="button" onClick={() => addRepeatableValue('exclusions', 'company_names')}>Add excluded company</button>
                  </div>
                </div>
              </section>

              {/* Adapter Hints */}
              <section className="spec-section">
                <h3>Adapter Hints</h3>
                <div className="form-grid">
                  <label className="checkbox-card">
                    <span>Prefer employee count</span>
                    <input
                      type="checkbox"
                      checked={form.adapter_hints.pdl.use_employee_count_over_size}
                      onChange={(e) => setField(['adapter_hints', 'pdl', 'use_employee_count_over_size'], e.target.checked)}
                    />
                  </label>
                  <label>
                    <span>Preferred industry field</span>
                    <input
                      type="text"
                      placeholder="industry_v2"
                      value={form.adapter_hints.pdl.industry_field_preference}
                      onChange={(e) => setField(['adapter_hints', 'pdl', 'industry_field_preference'], e.target.value)}
                    />
                  </label>
                  <label className="checkbox-card">
                    <span>Require industry or signal match</span>
                    <input
                      type="checkbox"
                      checked={form.adapter_hints.pdl.require_industry_or_signal_match}
                      onChange={(e) => setField(['adapter_hints', 'pdl', 'require_industry_or_signal_match'], e.target.checked)}
                    />
                  </label>
                  <label>
                    <span>Minimum signal match</span>
                    <input
                      type="number"
                      min="1"
                      max="5"
                      value={form.adapter_hints.pdl.signal_minimum_should_match}
                      onChange={(e) => setField(['adapter_hints', 'pdl', 'signal_minimum_should_match'], e.target.value)}
                    />
                  </label>
                </div>
              </section>

              {sizeWithoutEmployeeCountWarning && (
                <p className="notice warning">
                  Size bands are coarse and self-reported. Add an employee count range for tighter targeting.
                </p>
              )}
              {looseQueryWarning && (
                <p className="notice warning">
                  This ICP currently uses only broad evidence terms and no hard filters, so the compiled query will be loose.
                </p>
              )}

              <div className="inline-actions">
                <button type="submit" disabled={saving || !canSave}>
                  {saving ? 'Saving...' : form.id ? 'Update ICP' : 'Create ICP'}
                </button>
                <button className="ghost" type="button" disabled={saving} onClick={() => setForm(defaultIcpForm())}>
                  Reset form
                </button>
              </div>
            </form>
          )}

          {!form.id && icpCreateMode === 'json' && (
            <form className="stack" onSubmit={handleImportJson}>
              <p className="empty">Paste a full canonical ICP payload to create a new ICP from JSON.</p>

              <label>
                <span>ICP JSON payload</span>
                <textarea
                  rows={14}
                  placeholder='{"name":"US mid-market SaaS","priority":1,"geo":{"countries":["united states"]},"v":1}'
                  value={icpJsonInput}
                  onChange={(e) => setIcpJsonInput(e.target.value)}
                />
              </label>

              {icpJsonErrors.length > 0 && (
                <div className="notice error">
                  <strong>Import issues</strong>
                  <ul className="error-list">
                    {icpJsonErrors.map((issue) => (
                      <li key={issue}>{issue}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="inline-actions">
                <button type="submit" disabled={saving || !canImport}>
                  {saving ? 'Importing...' : 'Create From JSON'}
                </button>
                <button className="ghost" type="button" disabled={saving} onClick={() => setIcpJsonInput('')}>
                  Clear
                </button>
              </div>
            </form>
          )}
        </div>
      </section>
    </div>
  )
}
