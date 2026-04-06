import React, { useEffect, useReducer, useState } from 'react'
import { useUIStore } from '@/stores/uiStore'
import { useAuthStore } from '@/stores/authStore'
import { useSelectionStore } from '@/stores/selectionStore'
import { icps, accounts, contacts } from '@/lib/api'
import { SkeletonRows } from '@/workspace/views/Skeleton'
import { formatDate, truncate } from '@/workspace/views/utils'
import { cn } from '@/lib/utils'

// ── Column definitions ────────────────────────────────────────────────────────

const ICP_COLS = [
  { key: 'name',       label: 'Name',     sticky: true, render: (r) => r.name },
  { key: 'priority',   label: 'Priority', render: (r) => r.priority ?? '—' },
  { key: 'geo',        label: 'Regions',  render: (r) => (r.geo?.regions || []).join(', ') || '—' },
  { key: 'industry',   label: 'Industry', render: (r) => (r.industry_spec?.industries || []).join(', ') || '—' },
  { key: 'created_at', label: 'Added',    render: (r) => formatDate(r.created_at) },
]

const ACCOUNT_COLS = [
  { key: 'name',           label: 'Name',       sticky: true, render: (r) => r.display_name || r.name },
  { key: 'website',        label: 'Website',    render: (r) => r.website ? truncate(r.website, 30) : '—' },
  { key: 'industry',       label: 'Industry',   render: (r) => r.industry || '—' },
  { key: 'employee_count', label: 'Employees',  render: (r) => r.employee_count?.toLocaleString() ?? '—' },
  { key: 'country',        label: 'Country',    render: (r) => r.country || '—' },
  { key: 'crawl_status',   label: 'Crawl',      render: (r) => r.crawl_status || '—' },
  { key: 'captured_at',   label: 'Added',      render: (r) => formatDate(r.captured_at) },
]

const CONTACT_COLS = [
  { key: 'full_name',  label: 'Name',       sticky: true, render: (r) => r.full_name || '—' },
  { key: 'job_title',  label: 'Title',      render: (r) => r.job_title || '—' },
  { key: 'seniority',  label: 'Seniority',  render: (r) => r.seniority || '—' },
  { key: 'work_email', label: 'Email',      render: (r) => r.work_email || '—' },
  { key: 'department', label: 'Dept',       render: (r) => r.department || '—' },
  { key: 'created_at', label: 'Added',      render: (r) => formatDate(r.created_at) },
]

const COLS = { icps: ICP_COLS, accounts: ACCOUNT_COLS, contacts: CONTACT_COLS }

// ── Fetchers ──────────────────────────────────────────────────────────────────

function fetchData(token, sellerId, objectType, filters) {
  switch (objectType) {
    case 'icps':
      return icps.list(token, sellerId)
    case 'accounts':
      return accounts.list(token, sellerId)
    case 'contacts':
      return contacts.list(token, sellerId, { accountId: filters.accountId })
    default:
      return Promise.resolve([])
  }
}

// ── Reducer ───────────────────────────────────────────────────────────────────

function reducer(state, action) {
  switch (action.type) {
    case 'loading': return { loading: true, data: [], error: null }
    case 'loaded':  return { loading: false, data: action.data, error: null }
    case 'error':   return { loading: false, data: [], error: action.error }
    default:        return state
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ObjectTable({ sellerId, objectType }) {
  const token        = useAuthStore((s) => s.token)
  const openRecord   = useUIStore((s) => s.openRecord)
  const { toggleRecord, isSelected, getSelectedIds, clearSelection } = useSelectionStore()

  const [state, dispatch]   = useReducer(reducer, { loading: false, data: [], error: null })
  const [filters, setFilter] = useState({})

  const cols = COLS[objectType] || []

  useEffect(() => {
    clearSelection()
    if (!token || !sellerId || !objectType) return
    dispatch({ type: 'loading' })
    fetchData(token, sellerId, objectType, filters)
      .then((d) => dispatch({ type: 'loaded', data: Array.isArray(d) ? d : [] }))
      .catch((e) => dispatch({ type: 'error', error: e.message }))
  }, [token, sellerId, objectType, filters])

  const selectedCount = getSelectedIds().length

  return (
    <div className="flex flex-col h-full">
      {/* ── Toolbar ── */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-border flex-shrink-0">
        <span className="text-sm text-muted-foreground">
          {state.loading ? 'Loading…' : `${state.data.length} records`}
        </span>
        {selectedCount > 0 && (
          <span className="text-xs font-medium text-primary">
            {selectedCount} selected
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          {/* ICP filter for accounts/contacts */}
          {/* Simple placeholder — filter UI is block 5.4 */}
        </div>
      </div>

      {/* ── Table ── */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-sm border-collapse">
          <thead className="sticky top-0 bg-background z-10">
            <tr className="border-b border-border">
              {/* Checkbox column */}
              <th className="w-8 px-3 py-2.5" />
              {cols.map((col) => (
                <th
                  key={col.key}
                  className={cn(
                    'text-left px-3 py-2.5 font-medium text-muted-foreground whitespace-nowrap',
                    col.sticky && 'sticky left-8 bg-background z-20 shadow-[1px_0_0_0_hsl(var(--border))]',
                  )}
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {state.loading && <SkeletonRows cols={cols.length + 1} rows={8} />}
            {state.error && (
              <tr>
                <td colSpan={cols.length + 1} className="px-4 py-8 text-center text-sm text-destructive">
                  {state.error}
                </td>
              </tr>
            )}
            {!state.loading && !state.error && state.data.length === 0 && (
              <tr>
                <td colSpan={cols.length + 1} className="px-4 py-12 text-center text-sm text-muted-foreground">
                  No records found
                </td>
              </tr>
            )}
            {state.data.map((record) => {
              const selected = isSelected(record.id)
              return (
                <tr
                  key={record.id}
                  className={cn(
                    'border-b border-border transition-colors',
                    selected ? 'bg-accent' : 'hover:bg-accent/40',
                  )}
                >
                  {/* Checkbox */}
                  <td
                    className="w-8 px-3 py-2.5"
                    onClick={(e) => { e.stopPropagation(); toggleRecord(record.id, objectType, sellerId) }}
                  >
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() => {}}
                      className="h-3.5 w-3.5 rounded border-border accent-primary cursor-pointer"
                    />
                  </td>
                  {/* Data cells */}
                  {cols.map((col) => (
                    <td
                      key={col.key}
                      onClick={() => openRecord(record.id)}
                      className={cn(
                        'px-3 py-2.5 cursor-pointer max-w-[220px] truncate',
                        col.sticky && 'sticky left-8 bg-inherit z-10 shadow-[1px_0_0_0_hsl(var(--border))] font-medium',
                        'text-foreground',
                      )}
                    >
                      {col.render(record)}
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
