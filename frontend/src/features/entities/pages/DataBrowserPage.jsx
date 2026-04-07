import React, { useEffect, useMemo } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { setup, workspace } from '@/lib/api'
import { useAuth } from '@/features/auth/useAuth'
import { useEntityBrowserData } from '@/features/entities/hooks/useEntityBrowserData'
import { useTenantMemberships } from '@/features/tenants/hooks/useTenantMemberships'
import { useTenantStore } from '@/stores/tenantStore'

const TABS = ['sellers', 'icps', 'accounts', 'contacts', 'runs']

const TAB_META = {
  sellers: { label: 'Seller Profiles', idKey: 'seller_profile_id' },
  icps: { label: 'ICP Profiles', idKey: 'icp_profile_id' },
  accounts: { label: 'Accounts', idKey: 'account_id' },
  contacts: { label: 'Contacts', idKey: 'contact_id' },
  runs: { label: 'Workflow Runs', idKey: 'workflow_run_id' },
}

export default function DataBrowserPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { token } = useAuth()
  const activeTenantId = useTenantStore((state) => state.activeTenantId)
  const getActiveTenant = useTenantStore((state) => state.getActiveTenant)
  const getTenantContext = useTenantStore((state) => state.getTenantContext)
  const updateTenantContext = useTenantStore((state) => state.updateTenantContext)

  useTenantMemberships()

  const {
    loading,
    error,
    sellerProfiles,
    icpProfiles,
    accounts,
    contacts,
    workflowRuns,
  } = useEntityBrowserData()

  const activeTenant = getActiveTenant()
  const tenantContext = getTenantContext(activeTenantId)
  const activeTab = TABS.includes(searchParams.get('tab')) ? searchParams.get('tab') : 'accounts'
  const selectedId = searchParams.get('id') || ''

  const itemsByTab = useMemo(() => ({
    sellers: sellerProfiles,
    icps: icpProfiles,
    accounts,
    contacts,
    runs: workflowRuns,
  }), [accounts, contacts, icpProfiles, sellerProfiles, workflowRuns])

  const currentItems = itemsByTab[activeTab]
  const selectedItem = currentItems.find((item) => String(item[TAB_META[activeTab].idKey]) === selectedId) || null

  useEffect(() => {
    if (!currentItems.length || selectedItem) return

    const firstId = String(currentItems[0][TAB_META[activeTab].idKey])
    const nextParams = new URLSearchParams(searchParams)
    nextParams.set('tab', activeTab)
    nextParams.set('id', firstId)
    setSearchParams(nextParams, { replace: true })
  }, [activeTab, currentItems, searchParams, selectedItem, setSearchParams])

  const detailQuery = useQuery({
    queryKey: ['data-browser', activeTenantId, activeTab, selectedId],
    queryFn: () => {
      switch (activeTab) {
        case 'sellers':
          return setup.getSellerProfile(token, activeTenantId, selectedId)
        case 'icps':
          return setup.getIcpProfile(token, activeTenantId, selectedId)
        case 'accounts':
          return workspace.getAccount(token, activeTenantId, selectedId)
        case 'contacts':
          return workspace.getContact(token, activeTenantId, selectedId)
        case 'runs':
          return workspace.getWorkflowRun(token, activeTenantId, selectedId)
        default:
          return null
      }
    },
    enabled: Boolean(token && activeTenantId && selectedId),
  })

  if (!activeTenantId) {
    return <Navigate to="/workspace" replace />
  }

  function setTab(tab) {
    const nextParams = new URLSearchParams(searchParams)
    nextParams.set('tab', tab)
    nextParams.delete('id')
    setSearchParams(nextParams)
  }

  function selectRecord(id) {
    const nextParams = new URLSearchParams(searchParams)
    nextParams.set('tab', activeTab)
    nextParams.set('id', id)
    setSearchParams(nextParams)
  }

  function useInChat(record) {
    if (!activeTenantId || !record) return

    if (activeTab === 'sellers') {
      updateTenantContext(activeTenantId, {
        activeSellerProfileId: record.seller_profile_id,
        activeIcpProfileId: '',
        activeAccountId: '',
        activeContactId: '',
      })
    } else if (activeTab === 'icps') {
      updateTenantContext(activeTenantId, {
        activeSellerProfileId: record.seller_profile_id || tenantContext.activeSellerProfileId,
        activeIcpProfileId: record.icp_profile_id,
        activeAccountId: '',
        activeContactId: '',
      })
    } else if (activeTab === 'accounts') {
      updateTenantContext(activeTenantId, {
        activeAccountId: record.account_id,
        activeContactId: '',
      })
    } else if (activeTab === 'contacts') {
      updateTenantContext(activeTenantId, {
        activeAccountId: record.account_id || tenantContext.activeAccountId,
        activeContactId: record.contact_id,
      })
    } else if (activeTab === 'runs') {
      updateTenantContext(activeTenantId, {
        activeSellerProfileId: record.seller_profile_id || tenantContext.activeSellerProfileId,
        activeIcpProfileId: record.icp_profile_id || tenantContext.activeIcpProfileId,
        activeAccountId: record.selected_account_id || tenantContext.activeAccountId,
        activeContactId: record.selected_contact_id || tenantContext.activeContactId,
      })
    }

    navigate('/workspace')
  }

  return (
    <div className="min-h-screen bg-background px-4 py-6 text-foreground md:px-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="flex flex-col gap-4 rounded-3xl border border-border bg-card p-6 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
              Tenant Data
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">
              {activeTenant?.tenant_name || 'Active tenant'} data browser
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              Browse tenant-scoped records without leaving the chat-first workspace. You can pin
              any record back into chat context from here.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link to="/workspace" className="rounded-full border border-border px-4 py-2 text-sm">
              Back to chat
            </Link>
          </div>
        </header>

        <section className="grid gap-4 md:grid-cols-5">
          <StatCard label="Seller profiles" value={sellerProfiles.length} />
          <StatCard label="ICPs" value={icpProfiles.length} />
          <StatCard label="Accounts" value={accounts.length} />
          <StatCard label="Contacts" value={contacts.length} />
          <StatCard label="Workflow runs" value={workflowRuns.length} />
        </section>

        {(loading || error) && (
          <div className="rounded-2xl border border-border bg-card px-4 py-3 text-sm">
            {loading && <p className="text-muted-foreground">Loading tenant data...</p>}
            {error && <p className="text-destructive">{error}</p>}
          </div>
        )}

        <div className="grid gap-6 xl:grid-cols-[260px_minmax(0,1fr)_360px]">
          <aside className="rounded-3xl border border-border bg-card p-4">
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
              Browse
            </p>
            <div className="mt-4 space-y-2">
              {TABS.map((tab) => (
                <button
                  key={tab}
                  type="button"
                  className={[
                    'flex w-full items-center justify-between rounded-2xl border px-3 py-3 text-left transition',
                    activeTab === tab
                      ? 'border-foreground/20 bg-foreground text-background'
                      : 'border-border bg-background text-foreground hover:bg-muted/40',
                  ].join(' ')}
                  onClick={() => setTab(tab)}
                >
                  <span className="text-sm font-medium">{TAB_META[tab].label}</span>
                  <span className="text-xs opacity-70">{itemsByTab[tab].length}</span>
                </button>
              ))}
            </div>

            <div className="mt-6 rounded-2xl bg-muted/40 px-4 py-4 text-xs text-muted-foreground">
              <p>Seller: {tenantContext.activeSellerProfileId || 'None selected'}</p>
              <p className="mt-1">ICP: {tenantContext.activeIcpProfileId || 'None selected'}</p>
              <p className="mt-1">Account: {tenantContext.activeAccountId || 'None selected'}</p>
              <p className="mt-1">Contact: {tenantContext.activeContactId || 'None selected'}</p>
            </div>
          </aside>

          <section className="rounded-3xl border border-border bg-card p-4">
            <div className="flex items-center justify-between gap-4 border-b border-border pb-4">
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                  {TAB_META[activeTab].label}
                </p>
                <h2 className="mt-1 text-xl font-semibold tracking-tight">
                  {TAB_META[activeTab].label}
                </h2>
              </div>
              {currentItems.length > 0 && (
                <p className="text-sm text-muted-foreground">{currentItems.length} records</p>
              )}
            </div>

            <div className="mt-4 space-y-3">
              {currentItems.length === 0 && (
                <div className="rounded-2xl border border-dashed border-border bg-muted/20 px-4 py-6 text-sm text-muted-foreground">
                  No records available in this category yet.
                </div>
              )}

              {currentItems.map((item) => {
                const id = String(item[TAB_META[activeTab].idKey])
                return (
                  <button
                    key={id}
                    type="button"
                    className={[
                      'w-full rounded-2xl border px-4 py-4 text-left transition',
                      selectedId === id
                        ? 'border-foreground/20 bg-muted/40'
                        : 'border-border bg-background hover:bg-muted/20',
                    ].join(' ')}
                    onClick={() => selectRecord(id)}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-sm font-medium text-foreground">{getRecordTitle(activeTab, item)}</p>
                        <p className="mt-1 text-xs text-muted-foreground">{getRecordSubtitle(activeTab, item)}</p>
                      </div>
                      {activeTab === 'runs' && item.review_required && (
                        <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.18em] text-primary">
                          Review
                        </span>
                      )}
                    </div>
                  </button>
                )
              })}
            </div>
          </section>

          <aside className="rounded-3xl border border-border bg-card p-4">
            <div className="flex items-center justify-between gap-4 border-b border-border pb-4">
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                  Detail
                </p>
                <h2 className="mt-1 text-xl font-semibold tracking-tight">
                  {selectedItem ? getRecordTitle(activeTab, selectedItem) : 'Select a record'}
                </h2>
              </div>
              {selectedItem && (
                <button
                  type="button"
                  className="rounded-full border border-border px-4 py-2 text-sm"
                  onClick={() => useInChat(selectedItem)}
                >
                  Use in chat
                </button>
              )}
            </div>

            {!selectedItem && (
              <p className="mt-4 text-sm text-muted-foreground">
                Pick a record to inspect its detail and push it into the chat context.
              </p>
            )}

            {detailQuery.isLoading && (
              <p className="mt-4 text-sm text-muted-foreground">Loading detail...</p>
            )}

            {detailQuery.error && (
              <p className="mt-4 text-sm text-destructive">{detailQuery.error.message}</p>
            )}

            {detailQuery.data && (
              <div className="mt-4 space-y-4">
                <DetailSummary tab={activeTab} record={detailQuery.data} />
                {activeTab === 'runs' && <RunDetailExtras run={detailQuery.data} />}
              </div>
            )}
          </aside>
        </div>
      </div>
    </div>
  )
}

function StatCard({ label, value }) {
  return (
    <div className="rounded-3xl border border-border bg-card p-4">
      <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
      <p className="mt-3 text-2xl font-semibold">{value}</p>
    </div>
  )
}

function DetailSummary({ tab, record }) {
  if (tab === 'sellers') {
    return (
      <div className="space-y-3 text-sm">
        <KeyValue label="Company" value={record.company_name} />
        <KeyValue label="Domain" value={record.company_domain} />
        <TextBlock title="Product summary" body={record.product_summary} />
        <TextBlock title="Value proposition" body={record.value_proposition} />
        <TextBlock title="Target market summary" body={record.target_market_summary} />
      </div>
    )
  }

  if (tab === 'icps') {
    return (
      <div className="space-y-3 text-sm">
        <KeyValue label="Status" value={record.status} />
        <KeyValue label="Seller profile id" value={record.seller_profile_id} mono />
        <JsonBlock title="Criteria JSON" value={record.criteria_json} />
        <JsonBlock title="Exclusions JSON" value={record.exclusions_json} />
      </div>
    )
  }

  if (tab === 'accounts') {
    return (
      <div className="space-y-3 text-sm">
        <KeyValue label="Domain" value={record.domain} />
        <KeyValue label="Industry" value={record.industry} />
        <KeyValue label="Employee range" value={record.employee_range} />
        <KeyValue label="Status" value={record.status} />
        <TextBlock title="Fit summary" body={record.fit_summary} />
      </div>
    )
  }

  if (tab === 'contacts') {
    return (
      <div className="space-y-3 text-sm">
        <KeyValue label="Job title" value={record.job_title} />
        <KeyValue label="Email" value={record.email} />
        <KeyValue label="Phone" value={record.phone} />
        <KeyValue label="LinkedIn" value={record.linkedin_url} />
        <TextBlock title="Ranking summary" body={record.ranking_summary} />
      </div>
    )
  }

  return (
    <div className="space-y-3 text-sm">
      <KeyValue label="Workflow" value={record.workflow_type} />
      <KeyValue label="Status" value={record.status} />
      <KeyValue label="Outcome" value={record.outcome} />
      <TextBlock title="Visible summary" body={record.visible_summary} />
      <KeyValue label="Evidence count" value={record.evidence_count} />
      <KeyValue label="Review reason" value={record.review_reason} />
    </div>
  )
}

function RunDetailExtras({ run }) {
  return (
    <div className="space-y-4">
      <div className="rounded-2xl bg-muted/30 px-4 py-4 text-sm">
        <p className="font-medium text-foreground">Run-linked entities</p>
        <p className="mt-2 text-muted-foreground">Accounts: {run.account_ids?.length || 0}</p>
        <p className="mt-1 text-muted-foreground">Contacts: {run.contact_ids?.length || 0}</p>
        <p className="mt-1 text-muted-foreground">Artifacts: {run.artifact_ids?.length || 0}</p>
      </div>

      {run.latest_approval && (
        <div className="rounded-2xl border border-border px-4 py-4 text-sm">
          <p className="font-medium text-foreground">Latest approval</p>
          <p className="mt-2 text-muted-foreground">Decision: {run.latest_approval.decision}</p>
          <p className="mt-1 text-muted-foreground">Reviewed: {formatDate(run.latest_approval.reviewed_at)}</p>
          {run.latest_approval.rationale && (
            <p className="mt-2 text-muted-foreground">{run.latest_approval.rationale}</p>
          )}
        </div>
      )}

      {run.review_required && (
        <Link
          to={`/workspace/review/${run.workflow_run_id}`}
          className="inline-flex rounded-full border border-border px-4 py-2 text-sm"
        >
          Open review flow
        </Link>
      )}
    </div>
  )
}

function KeyValue({ label, value, mono = false }) {
  const resolvedValue = value === null || value === undefined || value === '' ? 'None' : value
  return (
    <div className="rounded-2xl border border-border px-3 py-3">
      <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
      <p className={['mt-2 text-sm text-foreground', mono ? 'break-all font-mono' : ''].join(' ')}>
        {resolvedValue}
      </p>
    </div>
  )
}

function TextBlock({ title, body }) {
  return (
    <div className="rounded-2xl border border-border px-3 py-3">
      <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">{title}</p>
      <p className="mt-2 text-sm leading-6 text-foreground">{body || 'None'}</p>
    </div>
  )
}

function JsonBlock({ title, value }) {
  return (
    <div className="rounded-2xl border border-border px-3 py-3">
      <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">{title}</p>
      <pre className="mt-2 overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">
        {JSON.stringify(value || {}, null, 2)}
      </pre>
    </div>
  )
}

function getRecordTitle(tab, item) {
  if (tab === 'sellers') return item.name
  if (tab === 'icps') return item.name
  if (tab === 'accounts') return item.name
  if (tab === 'contacts') return item.full_name || item.email || 'Unnamed contact'
  return item.workflow_type.replaceAll('_', ' ')
}

function getRecordSubtitle(tab, item) {
  if (tab === 'sellers') return item.company_name
  if (tab === 'icps') return `${item.status} ICP`
  if (tab === 'accounts') return item.domain || item.industry || 'No domain recorded'
  if (tab === 'contacts') return item.job_title || item.email || 'No contact details recorded'
  return `${item.status} - ${formatDate(item.updated_at)}`
}

function formatDate(value) {
  if (!value) return 'Not available'
  return new Date(value).toLocaleString()
}
