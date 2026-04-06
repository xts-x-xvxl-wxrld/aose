import React, { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { admin, identity } from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'

const EMPTY_FORM = {
  scope: 'tenant',
  agent_name: 'account_search_agent',
  instructions: '',
  system_prompt: '',
  model: '',
  change_note: '',
  activate: false,
}

export default function AdminPage() {
  const token = useAuthStore((state) => state.token)
  const user = useAuthStore((state) => state.user)
  const [searchParams, setSearchParams] = useSearchParams()

  const [tenants, setTenants] = useState([])
  const [platformTenants, setPlatformTenants] = useState([])
  const [platformOverview, setPlatformOverview] = useState(null)
  const [tenantOverview, setTenantOverview] = useState(null)
  const [runs, setRuns] = useState([])
  const [selectedRun, setSelectedRun] = useState(null)
  const [runEvents, setRunEvents] = useState([])
  const [llmCalls, setLlmCalls] = useState([])
  const [toolCalls, setToolCalls] = useState([])
  const [globalConfigs, setGlobalConfigs] = useState(null)
  const [tenantConfigs, setTenantConfigs] = useState(null)
  const [auditLogs, setAuditLogs] = useState([])
  const [form, setForm] = useState(EMPTY_FORM)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const selectedTenantId = searchParams.get('tenantId') || ''
  const selectedTenant = useMemo(
    () => tenants.find((tenant) => tenant.tenant_id === selectedTenantId) || null,
    [selectedTenantId, tenants],
  )

  useEffect(() => {
    if (!token) return
    let cancelled = false

    async function loadBase() {
      setLoading(true)
      setError('')
      try {
        const [tenantList, maybePlatformOverview, maybePlatformTenants] = await Promise.all([
          identity.listTenants(token),
          user?.isPlatformAdmin ? admin.getOverview(token) : Promise.resolve(null),
          user?.isPlatformAdmin ? admin.listPlatformTenants(token) : Promise.resolve({ tenants: [] }),
        ])

        if (cancelled) return
        const resolvedTenants = tenantList.tenants || []
        setTenants(resolvedTenants)
        setPlatformOverview(maybePlatformOverview)
        setPlatformTenants(maybePlatformTenants?.tenants || [])

        if (!selectedTenantId && resolvedTenants[0]?.tenant_id) {
          setSearchParams({ tenantId: resolvedTenants[0].tenant_id })
        }
      } catch (err) {
        if (!cancelled) setError(err.message || 'Unable to load admin context.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    loadBase()
    return () => {
      cancelled = true
    }
  }, [setSearchParams, selectedTenantId, token, user?.isPlatformAdmin])

  useEffect(() => {
    if (!token || !selectedTenantId) return
    let cancelled = false

    async function loadTenantScope() {
      setError('')
      try {
        const [overview, runList, tenantConfigScope, llmLogList, toolLogList, auditLogList, globalScope] = await Promise.all([
          admin.getTenantOverview(token, selectedTenantId),
          admin.listRuns(token, selectedTenantId),
          admin.listTenantConfigs(token, selectedTenantId),
          admin.listLlmCalls(token, selectedTenantId),
          admin.listToolCalls(token, selectedTenantId),
          admin.listAuditLogs(token, { tenantId: selectedTenantId }),
          user?.isPlatformAdmin ? admin.listGlobalConfigs(token) : Promise.resolve(null),
        ])
        if (cancelled) return
        setTenantOverview(overview)
        setRuns(runList.runs || [])
        setTenantConfigs(tenantConfigScope)
        setLlmCalls(llmLogList.calls || [])
        setToolCalls(toolLogList.calls || [])
        setAuditLogs(auditLogList.logs || [])
        if (globalScope) setGlobalConfigs(globalScope)
      } catch (err) {
        if (!cancelled) setError(err.message || 'Unable to load tenant admin data.')
      }
    }

    loadTenantScope()
    return () => {
      cancelled = true
    }
  }, [selectedTenantId, token, user?.isPlatformAdmin])

  useEffect(() => {
    if (!token || !selectedTenantId || !runs[0]) return
    const activeRunId = selectedRun?.run_id || runs[0].run_id
    let cancelled = false

    async function loadRunDetail() {
      try {
        const [runDetail, events] = await Promise.all([
          admin.getRun(token, selectedTenantId, activeRunId),
          admin.listRunEvents(token, selectedTenantId, activeRunId),
        ])
        if (cancelled) return
        setSelectedRun(runDetail)
        setRunEvents(events.events || [])
      } catch (err) {
        if (!cancelled) setError(err.message || 'Unable to load workflow run detail.')
      }
    }

    loadRunDetail()
    return () => {
      cancelled = true
    }
  }, [runs, selectedRun?.run_id, selectedTenantId, token])

  async function refreshConfigs() {
    if (!token || !selectedTenantId) return
    const [tenantScope, globalScope] = await Promise.all([
      admin.listTenantConfigs(token, selectedTenantId),
      user?.isPlatformAdmin ? admin.listGlobalConfigs(token) : Promise.resolve(globalConfigs),
    ])
    setTenantConfigs(tenantScope)
    if (globalScope) setGlobalConfigs(globalScope)
  }

  async function handleCreateConfig(event) {
    event.preventDefault()
    if (!token || saving || (form.scope === 'tenant' && !selectedTenantId)) return
    setSaving(true)
    setError('')
    try {
      const payload = {
        ...form,
        scope: undefined,
        model: form.model || null,
        instructions: form.instructions || null,
        system_prompt: form.system_prompt || null,
        change_note: form.change_note || null,
      }
      if (form.scope === 'global') {
        await admin.createGlobalConfigVersion(token, payload)
      } else {
        await admin.createTenantConfigVersion(token, selectedTenantId, payload)
      }
      setForm(EMPTY_FORM)
      await refreshConfigs()
    } catch (err) {
      setError(err.message || 'Unable to create tenant config version.')
    } finally {
      setSaving(false)
    }
  }

  async function handleActivate(versionId, mode = 'activate') {
    if (!token) return
    setSaving(true)
    setError('')
    try {
      if (mode === 'rollback') {
        await admin.rollbackConfigVersion(token, versionId)
      } else {
        await admin.activateConfigVersion(token, versionId)
      }
      await refreshConfigs()
    } catch (err) {
      setError(err.message || 'Unable to update config activation.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <PageShell><p className="text-sm text-muted-foreground">Loading admin workspace…</p></PageShell>
  }

  if (!user?.isPlatformAdmin && !tenants.some((tenant) => ['owner', 'admin'].includes(tenant.role))) {
    return (
      <PageShell>
        <div className="rounded-3xl border border-border bg-background p-6">
          <h1 className="text-xl font-semibold">Admin access required</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            This view is reserved for platform admins or tenant owners/admins.
          </p>
          <Link to="/" className="mt-4 inline-flex rounded-full border border-border px-3 py-2 text-sm">
            Back to workspace
          </Link>
        </div>
      </PageShell>
    )
  }

  return (
    <PageShell>
      <div className="space-y-6">
        <header className="flex flex-col gap-3 rounded-3xl border border-border bg-background p-6 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">Admin</p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight">Operations and agent configuration</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Inspect tenant workflow activity, recorded telemetry, and tenant-specific runtime overrides.
            </p>
          </div>
          <div className="flex gap-2">
            <Link to="/" className="rounded-full border border-border px-3 py-2 text-sm text-muted-foreground">
              Back to workspace
            </Link>
            <select
              className="rounded-full border border-border bg-background px-3 py-2 text-sm"
              value={selectedTenantId}
              onChange={(event) => setSearchParams({ tenantId: event.target.value })}
            >
              <option value="">Select tenant</option>
              {tenants.map((tenant) => (
                <option key={tenant.tenant_id} value={tenant.tenant_id}>{tenant.tenant_name}</option>
              ))}
            </select>
          </div>
        </header>

        {error && <div className="rounded-2xl border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}

        {user?.isPlatformAdmin && platformOverview && (
          <section className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
            <StatCard label="Tenants" value={platformOverview.total_tenants} />
            <StatCard label="Runs" value={platformOverview.total_runs} />
            <StatCard label="Active runs" value={platformOverview.active_runs} />
            <StatCard label="Failed runs" value={platformOverview.failed_runs} />
            <StatCard label="LLM calls" value={platformOverview.total_llm_calls} />
            <StatCard label="Tool calls" value={platformOverview.total_tool_calls} />
          </section>
        )}

        {user?.isPlatformAdmin && platformTenants.length > 0 && (
          <Panel title="Platform tenants" subtitle="Cross-tenant operational view for platform admins.">
            <SimpleTable
              columns={['Tenant', 'Members', 'Runs', 'Active', 'Failed', 'Status']}
              rows={platformTenants.map((tenant) => [
                tenant.tenant_name,
                tenant.active_member_count,
                tenant.total_runs,
                tenant.active_runs,
                tenant.failed_runs,
                tenant.tenant_status,
              ])}
            />
          </Panel>
        )}

        {selectedTenant && tenantOverview && (
          <section className="grid gap-4 md:grid-cols-3 xl:grid-cols-8">
            <StatCard label="Tenant" value={selectedTenant.tenant_name} />
            <StatCard label="Runs" value={tenantOverview.total_runs} />
            <StatCard label="Queued" value={tenantOverview.queued_runs} />
            <StatCard label="Running" value={tenantOverview.running_runs} />
            <StatCard label="Succeeded" value={tenantOverview.succeeded_runs} />
            <StatCard label="Failed" value={tenantOverview.failed_runs} />
            <StatCard label="LLM calls" value={tenantOverview.total_llm_calls} />
            <StatCard label="Tool calls" value={tenantOverview.total_tool_calls} />
          </section>
        )}

        {selectedTenantId && (
          <div className="grid gap-6 xl:grid-cols-[1.1fr_1fr]">
            <Panel title="Workflow runs" subtitle="Tenant-scoped run history and immutable config snapshots.">
              <SimpleTable
                columns={['Run id', 'Workflow', 'Status', 'Updated']}
                rows={runs.map((run) => [
                  <button key={run.run_id} type="button" className="font-mono text-left text-xs text-primary" onClick={() => setSelectedRun(run)}>
                    {String(run.run_id).slice(0, 8)}
                  </button>,
                  run.workflow_type,
                  run.status,
                  formatDate(run.updated_at),
                ])}
                emptyLabel="No workflow runs recorded yet."
              />
            </Panel>

            <Panel title="Run detail" subtitle="Selected workflow payloads, config snapshot, and event timeline.">
              {selectedRun ? (
                <div className="space-y-4">
                  <KeyValueGrid
                    items={[
                      ['Run id', selectedRun.run_id],
                      ['Workflow', selectedRun.workflow_type],
                      ['Status', selectedRun.status],
                      ['Error code', selectedRun.error_code || '—'],
                    ]}
                  />
                  <JsonBlock title="Config snapshot" value={selectedRun.config_snapshot_json} />
                  <JsonBlock title="Result payload" value={selectedRun.normalized_result_json} />
                  <JsonBlock title="Event timeline" value={runEvents} />
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Select a run to inspect its recorded state.</p>
              )}
            </Panel>
          </div>
        )}

        {selectedTenantId && (
          <div className="grid gap-6 xl:grid-cols-2">
            <Panel title="LLM telemetry" subtitle="Redacted model activity captured for tenant ops.">
              <SimpleTable
                columns={['Agent', 'Model', 'Status', 'Latency']}
                rows={llmCalls.map((call) => [
                  call.agent_name || '—',
                  call.model_name || '—',
                  call.status,
                  call.latency_ms != null ? `${call.latency_ms}ms` : '—',
                ])}
                emptyLabel="No LLM calls recorded yet."
              />
            </Panel>

            <Panel title="Tool telemetry" subtitle="Structured provider/tool activity linked to workflow runs.">
              <SimpleTable
                columns={['Tool', 'Provider', 'Status', 'Latency']}
                rows={toolCalls.map((call) => [
                  call.tool_name,
                  call.provider_name || '—',
                  call.status,
                  call.latency_ms != null ? `${call.latency_ms}ms` : '—',
                ])}
                emptyLabel="No tool calls recorded yet."
              />
            </Panel>
          </div>
        )}

        {selectedTenantId && tenantConfigs && (
          <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
            <Panel title="Tenant agent configs" subtitle="Effective config uses tenant override, then global override, then code default.">
              <div className="space-y-4">
                {(tenantConfigs.configs || []).map((config) => (
                  <div key={config.agent_name} className="rounded-2xl border border-border p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <h3 className="text-sm font-semibold">{config.agent_name}</h3>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Effective model: {config.effective.model || '—'}
                        </p>
                      </div>
                      {config.tenant_active && (
                        <button
                          type="button"
                          className="rounded-full border border-border px-3 py-1 text-xs"
                          onClick={() => handleActivate(config.tenant_active.id, 'rollback')}
                          disabled={saving}
                        >
                          Re-activate current
                        </button>
                      )}
                    </div>

                    <div className="mt-3 grid gap-3 lg:grid-cols-3">
                      <JsonCard title="Code default" value={config.code_default} />
                      <JsonCard title="Effective" value={config.effective} />
                      <JsonCard title="Active override" value={config.tenant_active?.payload || config.global_active?.payload || null} />
                    </div>

                    {(config.versions || []).length > 0 && (
                      <div className="mt-4 space-y-2">
                        {config.versions.map((version) => (
                          <div key={version.id} className="flex items-center justify-between rounded-xl border border-border px-3 py-2 text-sm">
                            <div>
                              <p className="font-medium">v{version.version} · {version.status}</p>
                              <p className="text-xs text-muted-foreground">{version.change_note || 'No change note.'}</p>
                            </div>
                            <div className="flex gap-2">
                              <button
                                type="button"
                                className="rounded-full border border-border px-3 py-1 text-xs"
                                onClick={() => handleActivate(version.id)}
                                disabled={saving}
                              >
                                Activate
                              </button>
                              <button
                                type="button"
                                className="rounded-full border border-border px-3 py-1 text-xs"
                                onClick={() => handleActivate(version.id, 'rollback')}
                                disabled={saving}
                              >
                                Rollback to this
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Panel>

            <Panel title="Create tenant override" subtitle="Create a new tenant-scoped config version.">
              <form className="space-y-3" onSubmit={handleCreateConfig}>
                {user?.isPlatformAdmin && (
                  <label className="block space-y-2">
                    <span className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">Scope</span>
                    <select
                      className="w-full rounded-xl border border-input bg-background px-3 py-2 text-sm"
                      value={form.scope}
                      onChange={(event) => setForm((current) => ({ ...current, scope: event.target.value }))}
                    >
                      <option value="tenant">Tenant override</option>
                      <option value="global">Global default override</option>
                    </select>
                  </label>
                )}
                <label className="block space-y-2">
                  <span className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">Agent</span>
                  <select
                    className="w-full rounded-xl border border-input bg-background px-3 py-2 text-sm"
                    value={form.agent_name}
                    onChange={(event) => setForm((current) => ({ ...current, agent_name: event.target.value }))}
                  >
                    {['orchestrator_agent', 'account_search_agent', 'account_research_agent', 'contact_search_agent'].map((name) => (
                      <option key={name} value={name}>{name}</option>
                    ))}
                  </select>
                </label>
                <LabeledField label="Model" value={form.model} onChange={(value) => setForm((current) => ({ ...current, model: value }))} placeholder="gpt-5.4-mini" />
                <LabeledTextarea label="Instructions" value={form.instructions} onChange={(value) => setForm((current) => ({ ...current, instructions: value }))} placeholder="Tenant-specific instructions override" />
                <LabeledTextarea label="System prompt" value={form.system_prompt} onChange={(value) => setForm((current) => ({ ...current, system_prompt: value }))} placeholder="Optional system prompt override" />
                <LabeledField label="Change note" value={form.change_note} onChange={(value) => setForm((current) => ({ ...current, change_note: value }))} placeholder="Why does this version exist?" />
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={form.activate}
                    onChange={(event) => setForm((current) => ({ ...current, activate: event.target.checked }))}
                  />
                  Activate immediately
                </label>
                <button
                  type="submit"
                  disabled={saving}
                  className="w-full rounded-xl border border-border bg-primary px-4 py-3 text-sm font-medium text-primary-foreground disabled:opacity-50"
                >
                  {saving ? 'Saving…' : `Create ${form.scope === 'global' ? 'global' : 'tenant'} config version`}
                </button>
              </form>
            </Panel>
          </div>
        )}

        {user?.isPlatformAdmin && globalConfigs && (
          <Panel title="Global agent configs" subtitle="Shared defaults applied when a tenant override is absent.">
            <div className="space-y-4">
              {(globalConfigs.configs || []).map((config) => (
                <div key={config.agent_name} className="rounded-2xl border border-border p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-semibold">{config.agent_name}</h3>
                      <p className="mt-1 text-xs text-muted-foreground">
                        Global active model: {config.global_active?.payload?.model || config.code_default.model || '—'}
                      </p>
                    </div>
                  </div>
                  <div className="mt-3 grid gap-3 lg:grid-cols-3">
                    <JsonCard title="Code default" value={config.code_default} />
                    <JsonCard title="Global active" value={config.global_active?.payload || null} />
                    <JsonCard title="Effective fallback" value={config.effective} />
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        )}

        {selectedTenantId && (
          <Panel title="Audit log" subtitle="Administrative changes recorded for this tenant scope.">
            <SimpleTable
              columns={['Action', 'Target', 'Actor', 'When']}
              rows={auditLogs.map((log) => [
                log.action,
                `${log.target_type}${log.target_id ? `:${String(log.target_id).slice(0, 8)}` : ''}`,
                String(log.actor_user_id).slice(0, 8),
                formatDate(log.created_at),
              ])}
              emptyLabel="No audit entries recorded yet."
            />
          </Panel>
        )}
      </div>
    </PageShell>
  )
}

function PageShell({ children }) {
  return <div className="min-h-screen bg-background px-4 py-6 md:px-6">{children}</div>
}

function Panel({ title, subtitle, children }) {
  return (
    <section className="rounded-3xl border border-border bg-background p-5">
      <div>
        <h2 className="text-lg font-semibold">{title}</h2>
        {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  )
}

function StatCard({ label, value }) {
  return (
    <div className="rounded-3xl border border-border bg-background p-4">
      <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
      <p className="mt-3 text-2xl font-semibold">{value}</p>
    </div>
  )
}

function SimpleTable({ columns, rows, emptyLabel = 'No records.' }) {
  if (!rows.length) {
    return <p className="text-sm text-muted-foreground">{emptyLabel}</p>
  }

  return (
    <div className="overflow-x-auto rounded-2xl border border-border">
      <table className="w-full text-sm">
        <thead className="bg-muted/40 text-left">
          <tr>
            {columns.map((column) => (
              <th key={column} className="px-3 py-2 font-medium text-muted-foreground">{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-t border-border">
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="px-3 py-2 align-top">{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function KeyValueGrid({ items }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {items.map(([label, value]) => (
        <div key={label} className="rounded-2xl border border-border px-3 py-3">
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
          <p className="mt-2 break-all text-sm">{String(value)}</p>
        </div>
      ))}
    </div>
  )
}

function JsonCard({ title, value }) {
  return (
    <div className="rounded-2xl border border-border p-3">
      <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">{title}</p>
      <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-xs text-muted-foreground">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  )
}

function JsonBlock({ title, value }) {
  return (
    <div className="rounded-2xl border border-border p-3">
      <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">{title}</p>
      <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  )
}

function LabeledField({ label, value, onChange, placeholder }) {
  return (
    <label className="block space-y-2">
      <span className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">{label}</span>
      <input
        className="w-full rounded-xl border border-input bg-background px-3 py-2 text-sm"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
      />
    </label>
  )
}

function LabeledTextarea({ label, value, onChange, placeholder }) {
  return (
    <label className="block space-y-2">
      <span className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">{label}</span>
      <textarea
        className="min-h-28 w-full rounded-xl border border-input bg-background px-3 py-2 text-sm"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
      />
    </label>
  )
}

function formatDate(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}
