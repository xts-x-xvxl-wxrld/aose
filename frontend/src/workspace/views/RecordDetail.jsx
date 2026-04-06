import React, { useEffect, useReducer } from 'react'
import { useAuthStore } from '@/stores/authStore'
import { icps, accounts, contacts } from '@/lib/api'
import { formatDate } from '@/workspace/views/utils'
import { cn } from '@/lib/utils'

function reducer(state, action) {
  switch (action.type) {
    case 'loading': return { loading: true, data: null, error: null }
    case 'loaded':  return { loading: false, data: action.data, error: null }
    case 'error':   return { loading: false, data: null, error: action.error }
    default:        return state
  }
}

function fetchRecord(token, sellerId, objectType, recordId) {
  switch (objectType) {
    case 'icps':
      return icps.get(token, sellerId, recordId)
    case 'accounts':
      return accounts.list(token, sellerId).then((list) => list.find((a) => a.id === recordId) || null)
    case 'contacts':
      return contacts.list(token, sellerId).then((list) => list.find((c) => c.id === recordId) || null)
    default:
      return Promise.resolve(null)
  }
}

export default function RecordDetail({ sellerId, objectType, recordId }) {
  const token = useAuthStore((s) => s.token)
  const [state, dispatch] = useReducer(reducer, { loading: false, data: null, error: null })

  useEffect(() => {
    if (!token || !sellerId || !objectType || !recordId) return
    dispatch({ type: 'loading' })
    fetchRecord(token, sellerId, objectType, recordId)
      .then((d) => dispatch({ type: 'loaded', data: d }))
      .catch((e) => dispatch({ type: 'error', error: e.message }))
  }, [token, sellerId, objectType, recordId])

  if (state.loading) return <DetailSkeleton />
  if (state.error)   return <div className="p-6 text-sm text-destructive">{state.error}</div>
  if (!state.data)   return <div className="p-6 text-sm text-muted-foreground">Record not found</div>

  const record = state.data

  return (
    <div className="h-full overflow-auto p-6 max-w-3xl">
      {objectType === 'icps'     && <ICPDetail record={record} />}
      {objectType === 'accounts' && <AccountDetail record={record} />}
      {objectType === 'contacts' && <ContactDetail record={record} />}
    </div>
  )
}

// ── ICP Detail ────────────────────────────────────────────────────────────────

function ICPDetail({ record }) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">{record.name}</h2>
        <p className="text-sm text-muted-foreground mt-0.5">Priority {record.priority} · Added {formatDate(record.created_at)}</p>
      </div>

      {record.fit_hypothesis && (
        <Section title="Fit Hypothesis">
          <p className="text-sm leading-relaxed">{record.fit_hypothesis}</p>
        </Section>
      )}

      <Section title="Geography">
        <JsonFields data={record.geo} />
      </Section>

      <Section title="Organisation">
        <JsonFields data={record.org} />
      </Section>

      <Section title="Industry">
        <JsonFields data={record.industry_spec} />
      </Section>

      <Section title="Capabilities">
        <JsonFields data={record.capability_spec} />
      </Section>

      <Section title="Signals">
        <JsonFields data={record.signal_spec} />
      </Section>

      {record.exclusions && Object.keys(record.exclusions).length > 0 && (
        <Section title="Exclusions">
          <JsonFields data={record.exclusions} />
        </Section>
      )}
    </div>
  )
}

// ── Account Detail ────────────────────────────────────────────────────────────

function AccountDetail({ record }) {
  const fields = [
    ['Name',          record.display_name || record.name],
    ['Website',       record.website],
    ['Domain',        record.normalized_domain],
    ['LinkedIn',      record.linkedin_url],
    ['Industry',      record.industry],
    ['Industry v2',   record.industry_v2],
    ['Type',          record.company_type],
    ['Employees',     record.employee_count?.toLocaleString()],
    ['Size',          record.size],
    ['Founded',       record.founded],
    ['Country',       record.country],
    ['Region',        record.region],
    ['Locality',      record.locality],
    ['Crawl Status',  record.crawl_status],
    ['Last Crawled',  formatDate(record.last_crawled_at)],
    ['Last Enriched', formatDate(record.last_enriched_at)],
    ['Captured',      formatDate(record.captured_at)],
    ['Source',        record.source],
  ]

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">{record.display_name || record.name}</h2>
        <p className="text-sm text-muted-foreground mt-0.5">{record.website || 'No website'}</p>
      </div>
      {record.selection_notes && (
        <Section title="Selection Notes">
          <p className="text-sm leading-relaxed">{record.selection_notes}</p>
        </Section>
      )}
      <Section title="Details">
        <FieldGrid fields={fields} />
      </Section>
    </div>
  )
}

// ── Contact Detail ────────────────────────────────────────────────────────────

function ContactDetail({ record }) {
  const fields = [
    ['Full Name',   record.full_name],
    ['First Name',  record.first_name],
    ['Last Name',   record.last_name],
    ['Job Title',   record.job_title],
    ['Seniority',   record.seniority],
    ['Department',  record.department],
    ['Work Email',  record.work_email],
    ['Phone',       record.phone_number],
    ['LinkedIn',    record.linkedin_url],
    ['Source',      record.source],
    ['Added',       formatDate(record.created_at)],
  ]

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">{record.full_name || 'Unknown'}</h2>
        <p className="text-sm text-muted-foreground mt-0.5">{record.job_title || 'No title'}</p>
      </div>
      <Section title="Details">
        <FieldGrid fields={fields} />
      </Section>
    </div>
  )
}

// ── Shared field primitives ───────────────────────────────────────────────────

function Section({ title, children }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">{title}</h3>
      {children}
    </div>
  )
}

function FieldGrid({ fields }) {
  const visible = fields.filter(([, v]) => v !== null && v !== undefined && v !== '')
  if (visible.length === 0) return <p className="text-sm text-muted-foreground">—</p>
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5">
      {visible.map(([label, value]) => (
        <React.Fragment key={label}>
          <dt className="text-sm text-muted-foreground whitespace-nowrap">{label}</dt>
          <dd className="text-sm text-foreground break-words">{value}</dd>
        </React.Fragment>
      ))}
    </dl>
  )
}

function JsonFields({ data }) {
  if (!data || typeof data !== 'object') return <p className="text-sm text-muted-foreground">—</p>
  const entries = Object.entries(data).filter(([, v]) => {
    if (v === null || v === undefined || v === '') return false
    if (Array.isArray(v) && v.length === 0) return false
    if (typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === 0) return false
    return true
  })
  if (entries.length === 0) return <p className="text-sm text-muted-foreground">—</p>
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5">
      {entries.map(([key, value]) => (
        <React.Fragment key={key}>
          <dt className="text-sm text-muted-foreground whitespace-nowrap capitalize">{key.replace(/_/g, ' ')}</dt>
          <dd className="text-sm text-foreground break-words">
            {Array.isArray(value) ? value.join(', ') : String(value)}
          </dd>
        </React.Fragment>
      ))}
    </dl>
  )
}

function DetailSkeleton() {
  return (
    <div className="p-6 space-y-4 animate-pulse">
      <div className="h-7 w-56 bg-muted rounded" />
      <div className="h-4 w-36 bg-muted rounded" />
      <div className="mt-6 space-y-2">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="h-4 bg-muted rounded" style={{ width: `${60 + (i % 3) * 15}%` }} />
        ))}
      </div>
    </div>
  )
}
