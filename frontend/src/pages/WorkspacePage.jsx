import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { setup, tenancy } from '@/lib/api'
import { useAuth } from '@/features/auth/useAuth'
import { useTenantMemberships } from '@/features/tenants/hooks/useTenantMemberships'
import { useAuthStore } from '@/stores/authStore'
import { useChatStore } from '@/stores/chatStore'
import { useTenantStore } from '@/stores/tenantStore'
import { getVisibleActions } from '@/workspace/actions/catalog'
import ChatWindow from '@/workspace/chat/ChatWindow'
import { useChat } from '@/workspace/hooks/useChat'
import { useWorkspaceData } from '@/workspace/hooks/useWorkspaceData'
import RightSidebar from '@/workspace/RightSidebar'

const EMPTY_TENANT_FORM = { name: '', slug: '' }
const EMPTY_SELLER_FORM = {
  name: '',
  company_name: '',
  company_domain: '',
  product_summary: '',
  value_proposition: '',
  target_market_summary: '',
}
const EMPTY_ICP_FORM = {
  name: '',
  status: 'active',
  criteria_json: '{\n  "industry": ["software"]\n}',
  exclusions_json: '',
}

export default function WorkspacePage() {
  const token = useAuthStore((state) => state.token)
  const { user, logout } = useAuth()

  const tenants = useTenantStore((state) => state.tenants)
  const loading = useTenantStore((state) => state.loading)
  const tenantError = useTenantStore((state) => state.error)
  const activeTenantId = useTenantStore((state) => state.activeTenantId)
  const setTenants = useTenantStore((state) => state.setTenants)
  const selectTenant = useTenantStore((state) => state.selectTenant)
  const upsertSellerProfile = useTenantStore((state) => state.upsertSellerProfile)
  const upsertIcpProfile = useTenantStore((state) => state.upsertIcpProfile)
  const updateTenantContext = useTenantStore((state) => state.updateTenantContext)
  const getTenantContext = useTenantStore((state) => state.getTenantContext)

  const clearChatError = useChatStore((state) => state.clearError)
  const clearThreadState = useChatStore((state) => state.clearThreadState)

  useTenantMemberships()

  const {
    messages,
    metaEvents,
    activeWorkflow,
    summaryText,
    isHydrating,
    isStreaming,
    streamingContent,
    error: chatError,
    submit,
    initializeTenantSession,
  } = useChat()

  const {
    loading: workspaceDataLoading,
    error: workspaceDataError,
    sellerProfiles,
    icpProfiles,
    accounts,
    contacts,
    workflowRuns,
    refreshBaseResources,
  } = useWorkspaceData()

  const [tenantForm, setTenantForm] = useState(EMPTY_TENANT_FORM)
  const [tenantFormBusy, setTenantFormBusy] = useState(false)
  const [tenantFormError, setTenantFormError] = useState('')

  const [sellerForm, setSellerForm] = useState(EMPTY_SELLER_FORM)
  const [sellerFormBusy, setSellerFormBusy] = useState(false)
  const [sellerFormError, setSellerFormError] = useState('')

  const [icpForm, setIcpForm] = useState(EMPTY_ICP_FORM)
  const [icpFormBusy, setIcpFormBusy] = useState(false)
  const [icpFormError, setIcpFormError] = useState('')

  useEffect(() => {
    if (!activeTenantId) {
      clearThreadState()
      return
    }
    initializeTenantSession(activeTenantId)
  }, [activeTenantId, clearThreadState, initializeTenantSession])

  const activeTenant = useMemo(
    () => tenants.find((tenant) => tenant.tenant_id === activeTenantId) || null,
    [activeTenantId, tenants],
  )
  const tenantContext = getTenantContext(activeTenantId)
  const activeSellerProfile = sellerProfiles.find(
    (profile) => profile.seller_profile_id === tenantContext.activeSellerProfileId,
  ) || null
  const activeIcpProfile = icpProfiles.find(
    (profile) => profile.icp_profile_id === tenantContext.activeIcpProfileId,
  ) || null
  const activeAccount = accounts.find(
    (account) => account.account_id === tenantContext.activeAccountId,
  ) || null
  const activeContact = contacts.find(
    (contact) => contact.contact_id === tenantContext.activeContactId,
  ) || null

  const promptActions = getVisibleActions({
    hasSellerProfile: Boolean(tenantContext.activeSellerProfileId),
    hasIcpProfile: Boolean(tenantContext.activeIcpProfileId),
    hasSelectedAccount: Boolean(tenantContext.activeAccountId),
    hasSelectedContact: Boolean(tenantContext.activeContactId),
    activeWorkflow,
  })

  const guidance = buildGuidance({
    hasTenant: Boolean(activeTenantId),
    hasSellerProfile: Boolean(tenantContext.activeSellerProfileId),
    hasIcpProfile: Boolean(tenantContext.activeIcpProfileId),
    hasSelectedAccount: Boolean(tenantContext.activeAccountId),
  })

  async function handleCreateTenant(event) {
    event.preventDefault()
    if (!token || tenantFormBusy) return

    setTenantFormBusy(true)
    setTenantFormError('')
    try {
      const createdTenant = await tenancy.createTenant(token, tenantForm)
      const nextTenants = [
        ...tenants,
        {
          tenant_id: createdTenant.tenant_id,
          tenant_name: createdTenant.name,
          role: createdTenant.creator_role,
          status: createdTenant.creator_status,
        },
      ]
      setTenants(nextTenants)
      selectTenant(createdTenant.tenant_id)
      setTenantForm(EMPTY_TENANT_FORM)
    } catch (err) {
      setTenantFormError(err.message || 'Unable to create tenant.')
    } finally {
      setTenantFormBusy(false)
    }
  }

  async function handleCreateSellerProfile(event) {
    event.preventDefault()
    if (!token || !activeTenantId || sellerFormBusy) return

    setSellerFormBusy(true)
    setSellerFormError('')
    try {
      const sellerProfile = await setup.createSellerProfile(token, activeTenantId, sellerForm)
      upsertSellerProfile(activeTenantId, sellerProfile)
      await refreshBaseResources()
      setSellerForm(EMPTY_SELLER_FORM)
    } catch (err) {
      setSellerFormError(err.message || 'Unable to create seller profile.')
    } finally {
      setSellerFormBusy(false)
    }
  }

  async function handleCreateIcpProfile(event) {
    event.preventDefault()
    if (!token || !activeTenantId || !tenantContext.activeSellerProfileId || icpFormBusy) return

    setIcpFormBusy(true)
    setIcpFormError('')
    try {
      const payload = {
        seller_profile_id: tenantContext.activeSellerProfileId,
        name: icpForm.name,
        status: icpForm.status,
        criteria_json: JSON.parse(icpForm.criteria_json),
        exclusions_json: icpForm.exclusions_json ? JSON.parse(icpForm.exclusions_json) : undefined,
      }
      const icpProfile = await setup.createIcpProfile(token, activeTenantId, payload)
      upsertIcpProfile(activeTenantId, icpProfile)
      await refreshBaseResources()
      setIcpForm(EMPTY_ICP_FORM)
    } catch (err) {
      setIcpFormError(err.message || 'Unable to create ICP profile.')
    } finally {
      setIcpFormBusy(false)
    }
  }

  const content = !activeTenant
    ? (
      <TenantSelectionState
        user={user}
        tenants={tenants}
        loading={loading}
        tenantError={tenantError}
        tenantForm={tenantForm}
        setTenantForm={setTenantForm}
        tenantFormBusy={tenantFormBusy}
        tenantFormError={tenantFormError}
        onCreateTenant={handleCreateTenant}
        onSelectTenant={selectTenant}
        onLogout={logout}
      />
    )
    : (
      <div className="grid h-screen grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)_360px]">
        <aside className="border-b border-border bg-sidebar/80 xl:border-b-0 xl:border-r">
          <WorkspaceRail
            user={user}
            tenant={activeTenant}
            tenants={tenants}
            tenantContext={tenantContext}
            activeSellerProfile={activeSellerProfile}
            activeIcpProfile={activeIcpProfile}
            activeAccount={activeAccount}
            activeContact={activeContact}
            sellerProfiles={sellerProfiles}
            icpProfiles={icpProfiles}
            accounts={accounts}
            contacts={contacts}
            workflowRuns={workflowRuns}
            workspaceDataLoading={workspaceDataLoading}
            workspaceDataError={workspaceDataError}
            onSelectTenant={(tenantId) => {
              clearChatError()
              selectTenant(tenantId)
            }}
            onUpdateContext={(changes) => updateTenantContext(activeTenantId, changes)}
            sellerForm={sellerForm}
            setSellerForm={setSellerForm}
            sellerFormBusy={sellerFormBusy}
            sellerFormError={sellerFormError}
            onCreateSellerProfile={handleCreateSellerProfile}
            icpForm={icpForm}
            setIcpForm={setIcpForm}
            icpFormBusy={icpFormBusy}
            icpFormError={icpFormError}
            onCreateIcpProfile={handleCreateIcpProfile}
            onLogout={logout}
          />
        </aside>

        <main className="min-h-0 bg-background">
          <ChatWindow
            tenantName={activeTenant.tenant_name}
            role={activeTenant.role}
            messages={messages}
            streamingContent={streamingContent}
            isHydrating={isHydrating}
            isStreaming={isStreaming}
            error={chatError}
            activeWorkflow={activeWorkflow}
            summaryText={summaryText}
            promptActions={promptActions}
            guidance={guidance}
            onDismissError={clearChatError}
            onSubmit={submit}
            onClearConversation={() => {
              clearChatError()
              updateTenantContext(activeTenantId, { threadId: '' })
              clearThreadState()
            }}
          />
        </main>

        <aside className="hidden border-l border-border bg-card/60 xl:block">
          <RightSidebar
            tenantName={activeTenant.tenant_name}
            tenantContext={tenantContext}
            activeWorkflow={activeWorkflow}
            activeAccount={activeAccount}
            activeContact={activeContact}
            workflowRuns={workflowRuns}
            messages={messages}
            metaEvents={metaEvents}
            streamingContent={streamingContent}
            isStreaming={isStreaming}
            promptActions={promptActions.slice(0, 3)}
            onSubmit={submit}
          />
        </aside>
      </div>
    )

  return (
    <div className="min-h-screen bg-background text-foreground">
      {content}
    </div>
  )
}

function TenantSelectionState({
  user,
  tenants,
  loading,
  tenantError,
  tenantForm,
  setTenantForm,
  tenantFormBusy,
  tenantFormError,
  onCreateTenant,
  onSelectTenant,
  onLogout,
}) {
  return (
    <div className="mx-auto flex min-h-screen max-w-6xl items-center px-6 py-12">
      <div className="grid w-full gap-8 lg:grid-cols-[1fr_420px]">
        <section className="space-y-6">
          <div className="space-y-3">
            <p className="text-sm font-medium uppercase tracking-[0.18em] text-muted-foreground">
              Tenant Entry
            </p>
            <h1 className="max-w-2xl text-4xl font-semibold tracking-tight">
              Choose a tenant before entering the chat workspace.
            </h1>
            <p className="max-w-xl text-sm leading-6 text-muted-foreground">
              Chat is the primary workflow entrypoint now, so the frontend blocks entry until a
              tenant is explicit. If you are starting from scratch, create a tenant first.
            </p>
          </div>

          <div className="rounded-[1.75rem] border border-border bg-card p-5 shadow-sm">
            <div className="flex items-center justify-between gap-4 border-b border-border pb-4">
              <div>
                <p className="text-sm font-medium text-foreground">{user?.displayName || user?.email || 'Workspace user'}</p>
                <p className="text-xs text-muted-foreground">Authenticated via Zitadel session</p>
              </div>
              <button
                className="rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground transition hover:text-foreground"
                onClick={onLogout}
              >
                Sign out
              </button>
            </div>

            <div className="mt-4 space-y-3">
              {loading && <p className="text-sm text-muted-foreground">Loading tenants…</p>}
              {tenantError && <p className="text-sm text-destructive">{tenantError}</p>}
              {!loading && tenants.length === 0 && (
                <p className="rounded-2xl border border-dashed border-border bg-muted/40 px-4 py-5 text-sm text-muted-foreground">
                  No active tenant memberships were returned for this user yet.
                </p>
              )}
              {tenants.map((tenant) => (
                <button
                  key={tenant.tenant_id}
                  className="flex w-full items-center justify-between rounded-2xl border border-border bg-background px-4 py-4 text-left transition hover:border-foreground/20 hover:bg-muted/40"
                  onClick={() => onSelectTenant(tenant.tenant_id)}
                >
                  <div>
                    <p className="text-sm font-medium text-foreground">{tenant.tenant_name}</p>
                    <p className="text-xs text-muted-foreground">
                      {tenant.role} · {tenant.status}
                    </p>
                  </div>
                  <span className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                    Enter
                  </span>
                </button>
              ))}
            </div>
          </div>
        </section>

        <section className="rounded-[1.75rem] border border-border bg-sidebar p-6 shadow-sm">
          <div className="space-y-2">
            <p className="text-sm font-medium uppercase tracking-[0.18em] text-muted-foreground">
              New Tenant
            </p>
            <h2 className="text-2xl font-semibold tracking-tight">Create a workspace</h2>
            <p className="text-sm text-muted-foreground">
              This uses the self-serve tenant creation route already exposed by the backend.
            </p>
          </div>

          <form className="mt-6 space-y-4" onSubmit={onCreateTenant}>
            <LabeledInput
              label="Tenant name"
              value={tenantForm.name}
              onChange={(value) => setTenantForm((current) => ({ ...current, name: value }))}
              placeholder="Acme Growth"
            />
            <LabeledInput
              label="Slug"
              value={tenantForm.slug}
              onChange={(value) => setTenantForm((current) => ({ ...current, slug: value }))}
              placeholder="acme-growth"
            />

            {tenantFormError && <p className="text-sm text-destructive">{tenantFormError}</p>}

            <button
              type="submit"
              disabled={tenantFormBusy || !tenantForm.name || !tenantForm.slug}
              className="w-full rounded-xl bg-primary px-4 py-3 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {tenantFormBusy ? 'Creating workspace…' : 'Create tenant'}
            </button>
          </form>
        </section>
      </div>
    </div>
  )
}

function WorkspaceRail({
  user,
  tenant,
  tenants,
  tenantContext,
  activeSellerProfile,
  activeIcpProfile,
  activeAccount,
  activeContact,
  sellerProfiles,
  icpProfiles,
  accounts,
  contacts,
  workflowRuns,
  workspaceDataLoading,
  workspaceDataError,
  onSelectTenant,
  onUpdateContext,
  sellerForm,
  setSellerForm,
  sellerFormBusy,
  sellerFormError,
  onCreateSellerProfile,
  icpForm,
  setIcpForm,
  icpFormBusy,
  icpFormError,
  onCreateIcpProfile,
  onLogout,
}) {
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border px-5 py-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
              Active Tenant
            </p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight">{tenant.tenant_name}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {tenant.role} membership · {user?.displayName || user?.email || 'Workspace user'}
            </p>
          </div>
          <button
            className="rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground transition hover:text-foreground"
            onClick={onLogout}
          >
            Sign out
          </button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Link
            to="/workspace/data"
            className="inline-flex rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground transition hover:text-foreground"
          >
            Browse data
          </Link>
          {(user?.isPlatformAdmin || ['owner', 'admin'].includes(tenant.role)) && (
            <Link
              to={`/admin?tenantId=${tenant.tenant_id}`}
              className="inline-flex rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground transition hover:text-foreground"
            >
              Open admin
            </Link>
          )}
        </div>

        {tenants.length > 1 && (
          <label className="mt-4 block space-y-2">
            <span className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
              Switch tenant
            </span>
            <select
              className="w-full rounded-xl border border-input bg-background px-3 py-2 text-sm"
              value={tenant.tenant_id}
              onChange={(event) => onSelectTenant(event.target.value)}
            >
              {tenants.map((item) => (
                <option key={item.tenant_id} value={item.tenant_id}>
                  {item.tenant_name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5">
        <section className="space-y-3 rounded-3xl border border-border bg-background p-4">
          <div>
            <p className="text-sm font-medium text-foreground">Active chat context</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              These IDs are packaged into chat turns so the backend can normalize tenant-scoped
              workflow input.
            </p>
          </div>

          <ContextSelect
            label="Seller profile"
            value={tenantContext.activeSellerProfileId}
            onChange={(value) => onUpdateContext({ activeSellerProfileId: value })}
            options={sellerProfiles.map((profile) => ({
              value: profile.seller_profile_id,
              label: profile.name,
            }))}
            fallbackLabel="Use a known seller profile id"
          />

          <ContextSelect
            label="ICP profile"
            value={tenantContext.activeIcpProfileId}
            onChange={(value) => onUpdateContext({ activeIcpProfileId: value })}
            options={icpProfiles.map((profile) => ({
              value: profile.icp_profile_id,
              label: profile.name,
            }))}
            fallbackLabel="Use a known ICP profile id"
          />

          <ContextSelect
            label="Selected account id"
            value={tenantContext.activeAccountId}
            onChange={(value) => onUpdateContext({ activeAccountId: value, activeContactId: '' })}
            options={accounts.map((account) => ({
              value: account.account_id,
              label: account.name,
            }))}
            fallbackLabel="Optional until you want research/contact search"
          />

          <ContextSelect
            label="Selected contact id"
            value={tenantContext.activeContactId}
            onChange={(value) => onUpdateContext({ activeContactId: value })}
            options={contacts.map((contact) => ({
              value: contact.contact_id,
              label: contact.full_name || contact.email || 'Unnamed contact',
            }))}
            fallbackLabel="Optional follow-up context"
          />

          <div className="rounded-2xl bg-muted/40 px-3 py-3 text-xs text-muted-foreground">
            <p>
              Seller: <span className="font-medium text-foreground">{activeSellerProfile?.name || tenantContext.activeSellerProfileId || 'Missing'}</span>
            </p>
            <p className="mt-1">
              ICP: <span className="font-medium text-foreground">{activeIcpProfile?.name || tenantContext.activeIcpProfileId || 'Missing'}</span>
            </p>
            <p className="mt-1">
              Account: <span className="font-medium text-foreground">{activeAccount?.name || tenantContext.activeAccountId || 'Optional'}</span>
            </p>
            <p className="mt-1">
              Contact: <span className="font-medium text-foreground">{activeContact?.full_name || tenantContext.activeContactId || 'Optional'}</span>
            </p>
          </div>
        </section>

        <section className="space-y-4 rounded-3xl border border-border bg-background p-4">
          <div>
            <p className="text-sm font-medium text-foreground">Workspace data</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              Tenant-scoped accounts, contacts, and recent workflow runs are now loaded directly
              from backend read APIs.
            </p>
          </div>

          {workspaceDataLoading && (
            <p className="text-sm text-muted-foreground">Loading tenant data…</p>
          )}

          {workspaceDataError && (
            <p className="text-sm text-destructive">{workspaceDataError}</p>
          )}

          <div className="grid gap-3 sm:grid-cols-3">
            <ResourceStat label="Seller profiles" value={sellerProfiles.length} />
            <ResourceStat label="Accounts" value={accounts.length} />
            <ResourceStat label="Contacts" value={contacts.length} />
          </div>

          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
              Recent workflow runs
            </p>
            {workflowRuns.length === 0 && (
              <p className="text-sm text-muted-foreground">No workflow runs recorded yet.</p>
            )}
            {workflowRuns.slice(0, 4).map((run) => (
              <div
                key={run.workflow_run_id}
                className="rounded-2xl border border-border px-3 py-3 transition hover:border-foreground/20 hover:bg-muted/40"
              >
                <button
                  type="button"
                  className="w-full text-left"
                  onClick={() => onUpdateContext({
                    activeAccountId: run.selected_account_id || tenantContext.activeAccountId,
                    activeContactId: run.selected_contact_id || '',
                  })}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-medium text-foreground">
                      {run.workflow_type.replaceAll('_', ' ')}
                    </span>
                    <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                      {run.status}
                    </span>
                  </div>
                  {run.visible_summary && (
                    <p className="mt-2 text-xs leading-5 text-muted-foreground">
                      {run.visible_summary}
                    </p>
                  )}
                </button>
                {run.review_required && (
                  <Link
                    to={`/workspace/review/${run.workflow_run_id}`}
                    className="mt-3 inline-flex rounded-full border border-border px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-muted-foreground"
                  >
                    Open review
                  </Link>
                )}
              </div>
            ))}
          </div>
        </section>

        <section className="space-y-4 rounded-3xl border border-border bg-background p-4">
          <div>
            <p className="text-sm font-medium text-foreground">Seller setup</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              Create a seller profile here, or paste an existing seller profile id above if the
              record already exists in the backend.
            </p>
          </div>

          <form className="space-y-3" onSubmit={onCreateSellerProfile}>
            <LabeledInput
              label="Profile name"
              value={sellerForm.name}
              onChange={(value) => setSellerForm((current) => ({ ...current, name: value }))}
              placeholder="Primary seller"
            />
            <LabeledInput
              label="Company name"
              value={sellerForm.company_name}
              onChange={(value) => setSellerForm((current) => ({ ...current, company_name: value }))}
              placeholder="Acme"
            />
            <LabeledInput
              label="Company domain"
              value={sellerForm.company_domain}
              onChange={(value) => setSellerForm((current) => ({ ...current, company_domain: value }))}
              placeholder="acme.example"
            />
            <LabeledTextarea
              label="Product summary"
              value={sellerForm.product_summary}
              onChange={(value) => setSellerForm((current) => ({ ...current, product_summary: value }))}
              placeholder="What does the seller actually offer?"
            />
            <LabeledTextarea
              label="Value proposition"
              value={sellerForm.value_proposition}
              onChange={(value) => setSellerForm((current) => ({ ...current, value_proposition: value }))}
              placeholder="Why should the target care?"
            />
            <LabeledTextarea
              label="Target market summary"
              value={sellerForm.target_market_summary}
              onChange={(value) => setSellerForm((current) => ({ ...current, target_market_summary: value }))}
              placeholder="Optional audience framing"
            />

            {sellerFormError && <p className="text-sm text-destructive">{sellerFormError}</p>}

            <button
              type="submit"
              disabled={sellerFormBusy || !sellerForm.name || !sellerForm.company_name || !sellerForm.product_summary || !sellerForm.value_proposition}
              className="w-full rounded-xl border border-border bg-primary px-4 py-3 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {sellerFormBusy ? 'Creating seller profile…' : 'Create seller profile'}
            </button>
          </form>
        </section>

        <section className="space-y-4 rounded-3xl border border-border bg-background p-4">
          <div>
            <p className="text-sm font-medium text-foreground">ICP setup</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              Keep using the existing form-based setup path in v1. The current selected seller
              profile is required for new ICP creation.
            </p>
          </div>

          <form className="space-y-3" onSubmit={onCreateIcpProfile}>
            <LabeledInput
              label="ICP name"
              value={icpForm.name}
              onChange={(value) => setIcpForm((current) => ({ ...current, name: value }))}
              placeholder="Primary ICP"
            />

            <label className="block space-y-2">
              <span className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                Status
              </span>
              <select
                className="w-full rounded-xl border border-input bg-background px-3 py-2 text-sm"
                value={icpForm.status}
                onChange={(event) => setIcpForm((current) => ({ ...current, status: event.target.value }))}
              >
                <option value="draft">draft</option>
                <option value="active">active</option>
                <option value="archived">archived</option>
              </select>
            </label>

            <LabeledTextarea
              label="Criteria JSON"
              value={icpForm.criteria_json}
              onChange={(value) => setIcpForm((current) => ({ ...current, criteria_json: value }))}
              placeholder='{"industry":["software"]}'
            />
            <LabeledTextarea
              label="Exclusions JSON"
              value={icpForm.exclusions_json}
              onChange={(value) => setIcpForm((current) => ({ ...current, exclusions_json: value }))}
              placeholder='{"geography":["antarctica"]}'
            />

            {icpFormError && <p className="text-sm text-destructive">{icpFormError}</p>}

            <button
              type="submit"
              disabled={icpFormBusy || !tenantContext.activeSellerProfileId || !icpForm.name || !icpForm.criteria_json}
              className="w-full rounded-xl border border-border bg-primary px-4 py-3 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {icpFormBusy ? 'Creating ICP profile…' : 'Create ICP profile'}
            </button>
          </form>
        </section>
      </div>
    </div>
  )
}

function ResourceStat({ label, value }) {
  return (
    <div className="rounded-2xl border border-border px-3 py-3">
      <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </p>
      <p className="mt-2 text-xl font-semibold text-foreground">{value}</p>
    </div>
  )
}

function ContextSelect({ label, value, onChange, options, fallbackLabel }) {
  return (
    <div className="space-y-2">
      <label className="block">
        <span className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
          {label}
        </span>
        <input
          className="mt-2 w-full rounded-xl border border-input bg-background px-3 py-2 text-sm"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={fallbackLabel}
        />
      </label>
      {options.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              className={[
                'rounded-full border px-3 py-1 text-xs transition',
                value === option.value
                  ? 'border-foreground/20 bg-foreground text-background'
                  : 'border-border text-muted-foreground hover:text-foreground',
              ].join(' ')}
              onClick={() => onChange(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function LabeledInput({ label, value, onChange, placeholder }) {
  return (
    <label className="block space-y-2">
      <span className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </span>
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
      <span className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </span>
      <textarea
        className="min-h-28 w-full rounded-xl border border-input bg-background px-3 py-2 text-sm"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
      />
    </label>
  )
}

function buildGuidance({
  hasTenant,
  hasSellerProfile,
  hasIcpProfile,
  hasSelectedAccount,
}) {
  if (!hasTenant) {
    return 'Pick a tenant before entering the chat workspace.'
  }
  if (!hasSellerProfile) {
    return 'Create a seller profile or paste an existing seller profile id to unlock workflow-safe chat context.'
  }
  if (!hasIcpProfile) {
    return 'Create an ICP profile or paste an existing ICP profile id before starting account search.'
  }
  if (!hasSelectedAccount) {
    return 'Account search can start now. Add an account id later when you want account research or contact search.'
  }
  return 'Chat is ready for account search, account research, and contact search using the current tenant context.'
}
