import React, { useMemo, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'

import { review, workspace } from '@/lib/api'
import { useAuth } from '@/features/auth/useAuth'
import { useTenantStore } from '@/stores/tenantStore'

const DECISIONS = [
  { value: 'approved', label: 'Approve' },
  { value: 'needs_changes', label: 'Needs changes' },
  { value: 'rejected', label: 'Reject' },
]

export default function ReviewPage() {
  const { runId } = useParams()
  const queryClient = useQueryClient()
  const { token } = useAuth()
  const activeTenantId = useTenantStore((state) => state.activeTenantId)
  const getActiveTenant = useTenantStore((state) => state.getActiveTenant)
  const [decision, setDecision] = useState('approved')
  const [rationale, setRationale] = useState('')
  const [artifactId, setArtifactId] = useState('')

  const activeTenant = getActiveTenant()

  const runQuery = useQuery({
    queryKey: ['review', activeTenantId, runId, 'run'],
    queryFn: () => workspace.getWorkflowRun(token, activeTenantId, runId),
    enabled: Boolean(token && activeTenantId && runId),
  })

  const evidenceQuery = useQuery({
    queryKey: ['review', activeTenantId, runId, 'evidence'],
    queryFn: () => review.listEvidence(token, activeTenantId, runId),
    enabled: Boolean(token && activeTenantId && runId),
  })

  const artifactQueries = useQueries({
    queries: (runQuery.data?.artifact_ids || []).map((currentArtifactId) => ({
      queryKey: ['review', activeTenantId, currentArtifactId, 'artifact'],
      queryFn: () => review.getArtifact(token, activeTenantId, currentArtifactId),
      enabled: Boolean(token && activeTenantId && currentArtifactId),
    })),
  })

  const artifacts = useMemo(
    () => artifactQueries.map((query) => query.data).filter(Boolean),
    [artifactQueries],
  )

  const approvalMutation = useMutation({
    mutationFn: (payload) => review.submitApproval(token, activeTenantId, runId, payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['review', activeTenantId, runId] }),
        queryClient.invalidateQueries({ queryKey: ['workspace', activeTenantId, 'workflowRuns'] }),
        queryClient.invalidateQueries({ queryKey: ['browser', activeTenantId, 'workflowRuns'] }),
      ])
      setRationale('')
    },
  })

  if (!activeTenantId) {
    return <Navigate to="/workspace" replace />
  }

  const rationaleRequired = decision === 'rejected' || decision === 'needs_changes'

  async function handleSubmit(event) {
    event.preventDefault()
    await approvalMutation.mutateAsync({
      decision,
      rationale: rationale.trim() || undefined,
      artifact_id: artifactId || undefined,
    })
  }

  return (
    <div className="min-h-screen bg-background px-4 py-6 text-foreground md:px-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="flex flex-col gap-4 rounded-3xl border border-border bg-card p-6 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
              Review Flow
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">
              {activeTenant?.tenant_name || 'Active tenant'} review
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              Inspect the workflow summary, artifacts, and evidence before submitting a decision.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link to="/workspace" className="rounded-full border border-border px-4 py-2 text-sm">
              Back to chat
            </Link>
            <Link to="/workspace/data?tab=runs" className="rounded-full border border-border px-4 py-2 text-sm">
              View all runs
            </Link>
          </div>
        </header>

        {(runQuery.isLoading || evidenceQuery.isLoading) && (
          <div className="rounded-2xl border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
            Loading review state...
          </div>
        )}

        {(runQuery.error || evidenceQuery.error || approvalMutation.error) && (
          <div className="rounded-2xl border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {runQuery.error?.message || evidenceQuery.error?.message || approvalMutation.error?.message}
          </div>
        )}

        {runQuery.data && (
          <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
            <section className="space-y-6 rounded-3xl border border-border bg-card p-5">
              <div className="grid gap-4 md:grid-cols-2">
                <StatCard label="Workflow" value={runQuery.data.workflow_type} />
                <StatCard label="Status" value={runQuery.data.status} />
                <StatCard label="Review required" value={runQuery.data.review_required ? 'yes' : 'no'} />
                <StatCard label="Evidence count" value={String(runQuery.data.evidence_count)} />
              </div>

              <Panel title="Run summary">
                <p className="text-sm leading-6 text-foreground">
                  {runQuery.data.visible_summary || 'No visible summary recorded for this run yet.'}
                </p>
                {runQuery.data.review_reason && (
                  <p className="mt-3 text-sm text-muted-foreground">
                    Review reason: {runQuery.data.review_reason}
                  </p>
                )}
              </Panel>

              {runQuery.data.latest_approval && (
                <Panel title="Latest decision">
                  <p className="text-sm text-foreground">{runQuery.data.latest_approval.decision}</p>
                  {runQuery.data.latest_approval.rationale && (
                    <p className="mt-2 text-sm text-muted-foreground">
                      {runQuery.data.latest_approval.rationale}
                    </p>
                  )}
                  <p className="mt-2 text-xs text-muted-foreground">
                    Reviewed at {formatDate(runQuery.data.latest_approval.reviewed_at)}
                  </p>
                </Panel>
              )}

              <Panel title="Artifacts">
                {artifacts.length === 0 && (
                  <p className="text-sm text-muted-foreground">No artifacts recorded for this run.</p>
                )}

                <div className="space-y-4">
                  {artifacts.map((artifact) => (
                    <div key={artifact.artifact_id} className="rounded-2xl border border-border px-4 py-4">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <p className="text-sm font-medium text-foreground">{artifact.title}</p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {artifact.artifact_type} - {artifact.format}
                          </p>
                        </div>
                        <button
                          type="button"
                          className={[
                            'rounded-full border px-3 py-1 text-xs',
                            artifactId === artifact.artifact_id
                              ? 'border-foreground/20 bg-foreground text-background'
                              : 'border-border text-muted-foreground',
                          ].join(' ')}
                          onClick={() => setArtifactId(String(artifact.artifact_id))}
                        >
                          Target this artifact
                        </button>
                      </div>

                      {artifact.content_markdown && (
                        <pre className="mt-4 max-h-72 overflow-auto whitespace-pre-wrap rounded-2xl bg-muted/30 px-4 py-4 text-xs text-muted-foreground">
                          {artifact.content_markdown}
                        </pre>
                      )}

                      {!artifact.content_markdown && artifact.content_json && (
                        <pre className="mt-4 max-h-72 overflow-auto whitespace-pre-wrap rounded-2xl bg-muted/30 px-4 py-4 text-xs text-muted-foreground">
                          {JSON.stringify(artifact.content_json, null, 2)}
                        </pre>
                      )}

                      {artifact.storage_url && (
                        <a
                          href={artifact.storage_url}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-3 inline-flex text-xs text-primary"
                        >
                          Open stored artifact
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              </Panel>
            </section>

            <section className="space-y-6 rounded-3xl border border-border bg-card p-5">
              <Panel title="Evidence">
                {(evidenceQuery.data?.evidence || []).length === 0 && (
                  <p className="text-sm text-muted-foreground">No evidence returned for this run.</p>
                )}

                <div className="space-y-3">
                  {(evidenceQuery.data?.evidence || []).map((item) => (
                    <div key={item.evidence_id} className="rounded-2xl border border-border px-4 py-4">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <p className="text-sm font-medium text-foreground">
                            {item.title || item.provider_name || item.source_type}
                          </p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {item.provider_name || 'Unknown provider'} - {item.source_type}
                          </p>
                        </div>
                        {item.confidence_score != null && (
                          <span className="rounded-full bg-muted px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                            {Math.round(item.confidence_score * 100)}%
                          </span>
                        )}
                      </div>
                      {item.snippet_text && (
                        <p className="mt-3 text-sm leading-6 text-foreground">{item.snippet_text}</p>
                      )}
                      {item.source_url && (
                        <a
                          href={item.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-3 inline-flex text-xs text-primary"
                        >
                          Open source
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              </Panel>

              <Panel title="Decision">
                <form className="space-y-4" onSubmit={handleSubmit}>
                  <div className="flex flex-wrap gap-2">
                    {DECISIONS.map((entry) => (
                      <button
                        key={entry.value}
                        type="button"
                        className={[
                          'rounded-full border px-4 py-2 text-sm transition',
                          decision === entry.value
                            ? 'border-foreground/20 bg-foreground text-background'
                            : 'border-border text-foreground',
                        ].join(' ')}
                        onClick={() => setDecision(entry.value)}
                      >
                        {entry.label}
                      </button>
                    ))}
                  </div>

                  <label className="block space-y-2">
                    <span className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                      Rationale
                    </span>
                    <textarea
                      className="min-h-32 w-full rounded-2xl border border-input bg-background px-3 py-3 text-sm"
                      value={rationale}
                      onChange={(event) => setRationale(event.target.value)}
                      placeholder="Required for rejection or needs changes."
                    />
                  </label>
                  {rationaleRequired && !rationale.trim() && (
                    <p className="text-xs text-destructive">
                      Rationale is required for rejection and needs changes decisions.
                    </p>
                  )}

                  <button
                    type="submit"
                    disabled={approvalMutation.isPending || (rationaleRequired && !rationale.trim())}
                    className="w-full rounded-2xl bg-primary px-4 py-3 text-sm font-medium text-primary-foreground disabled:opacity-50"
                  >
                    {approvalMutation.isPending ? 'Submitting decision...' : 'Submit decision'}
                  </button>
                </form>
              </Panel>
            </section>
          </div>
        )}
      </div>
    </div>
  )
}

function Panel({ title, children }) {
  return (
    <div className="rounded-2xl border border-border px-4 py-4">
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      <div className="mt-4">{children}</div>
    </div>
  )
}

function StatCard({ label, value }) {
  return (
    <div className="rounded-2xl border border-border px-4 py-4">
      <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
      <p className="mt-3 text-xl font-semibold text-foreground">{value}</p>
    </div>
  )
}

function formatDate(value) {
  if (!value) return 'Not available'
  return new Date(value).toLocaleString()
}
