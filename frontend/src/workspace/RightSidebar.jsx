import React from 'react'
import { Link } from 'react-router-dom'

import ChatInput from '@/workspace/chat/ChatInput'
import MessageList from '@/workspace/chat/MessageList'

export default function RightSidebar({
  tenantName,
  tenantContext,
  activeWorkflow,
  activeAccount,
  activeContact,
  workflowRuns,
  messages,
  metaEvents,
  streamingContent,
  isStreaming,
  promptActions,
  onSubmit,
}) {
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border px-4 py-4">
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
          Compact Chat
        </p>
        <h3 className="mt-2 text-lg font-semibold tracking-tight">{tenantName}</h3>
        <div className="mt-3 flex flex-wrap gap-2">
          {tenantContext.activeSellerProfileId && (
            <span className="rounded-full bg-muted px-2.5 py-1 text-[11px] text-muted-foreground">
              seller ready
            </span>
          )}
          {tenantContext.activeIcpProfileId && (
            <span className="rounded-full bg-muted px-2.5 py-1 text-[11px] text-muted-foreground">
              icp ready
            </span>
          )}
          {tenantContext.activeAccountId && (
            <span className="rounded-full bg-muted px-2.5 py-1 text-[11px] text-muted-foreground">
              account pinned
            </span>
          )}
          {tenantContext.activeContactId && (
            <span className="rounded-full bg-muted px-2.5 py-1 text-[11px] text-muted-foreground">
              contact pinned
            </span>
          )}
          {activeWorkflow && (
            <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-medium text-primary">
              {activeWorkflow.replaceAll('_', ' ')}
            </span>
          )}
        </div>
      </div>

      {promptActions.length > 0 && (
        <div className="border-b border-border px-4 py-3">
          <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Prompt Actions
          </p>
          <div className="flex flex-wrap gap-2">
            {promptActions.map((action) => (
              <button
                key={action.id}
                className="rounded-full border border-border px-2.5 py-1 text-[11px] text-muted-foreground transition hover:text-foreground"
                onClick={() => onSubmit(action.prompt)}
                disabled={isStreaming}
              >
                {action.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <MessageList
        messages={messages}
        streamingContent={streamingContent}
        isStreaming={isStreaming}
        compact
        emptyTitle="Shared session"
        emptyBody="This sidebar mirrors the same tenant thread as the full chat panel."
      />

      <ChatInput
        onSubmit={onSubmit}
        isStreaming={isStreaming}
        compact
        placeholder="Send a quick follow-up"
      />

      <div className="border-t border-border px-4 py-3">
        <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
          Active data context
        </p>
        <div className="mt-3 space-y-2 text-xs text-muted-foreground">
          <p>
            Account: <span className="font-medium text-foreground">{activeAccount?.name || tenantContext.activeAccountId || 'None selected'}</span>
          </p>
          <p>
            Contact: <span className="font-medium text-foreground">{activeContact?.full_name || tenantContext.activeContactId || 'None selected'}</span>
          </p>
        </div>
      </div>

      <div className="border-t border-border px-4 py-3">
        <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
          Run Events
        </p>
        <div className="mt-3 max-h-56 space-y-2 overflow-y-auto">
          {metaEvents.length === 0 && (
            <p className="text-xs text-muted-foreground">No projected events yet.</p>
          )}
          {metaEvents.map((event, index) => (
            <div key={`${event.workflow_run_id}-${event.type}-${index}`} className="rounded-2xl border border-border bg-background px-3 py-2">
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs font-medium text-foreground">{event.type.replaceAll('_', ' ')}</span>
                <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                  {event.workflow_status || 'event'}
                </span>
              </div>
              {event.payload?.tool_name && (
                <p className="mt-1 text-xs text-muted-foreground">Tool: {event.payload.tool_name}</p>
              )}
              {event.payload?.to_agent && (
                <p className="mt-1 text-xs text-muted-foreground">To: {event.payload.to_agent}</p>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-border px-4 py-3">
        <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
          Recent runs
        </p>
        <div className="mt-3 max-h-56 space-y-2 overflow-y-auto">
          {workflowRuns.length === 0 && (
            <p className="text-xs text-muted-foreground">No workflow runs loaded yet.</p>
          )}
          {workflowRuns.slice(0, 5).map((run) => (
            <div key={run.workflow_run_id} className="rounded-2xl border border-border bg-background px-3 py-2">
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs font-medium text-foreground">
                  {run.workflow_type.replaceAll('_', ' ')}
                </span>
                <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                  {run.status}
                </span>
              </div>
              {run.visible_summary && (
                <p className="mt-1 text-xs text-muted-foreground">{run.visible_summary}</p>
              )}
              {run.review_required && (
                <Link
                  to={`/workspace/review/${run.workflow_run_id}`}
                  className="mt-2 inline-flex rounded-full border border-border px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-muted-foreground"
                >
                  Review
                </Link>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
