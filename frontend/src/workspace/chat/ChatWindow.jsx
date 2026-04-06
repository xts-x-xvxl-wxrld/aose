import React from 'react'
import { RefreshCcw, WandSparkles } from 'lucide-react'

import MessageList from '@/workspace/chat/MessageList'
import ChatInput from '@/workspace/chat/ChatInput'

export default function ChatWindow({
  tenantName,
  role,
  messages,
  streamingContent,
  isHydrating,
  isStreaming,
  error,
  activeWorkflow,
  summaryText,
  promptActions,
  guidance,
  onDismissError,
  onSubmit,
  onClearConversation,
}) {
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border px-6 py-5">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-border bg-card px-3 py-1 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                Chat Workspace
              </span>
              <span className="rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground">
                {role}
              </span>
              {activeWorkflow && (
                <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
                  {activeWorkflow.replaceAll('_', ' ')}
                </span>
              )}
            </div>
            <div>
              <h2 className="text-2xl font-semibold tracking-tight">{tenantName}</h2>
              <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">
                {guidance}
              </p>
            </div>
          </div>

          <button
            className="inline-flex items-center gap-2 rounded-full border border-border px-3 py-2 text-xs text-muted-foreground transition hover:text-foreground"
            onClick={onClearConversation}
          >
            <RefreshCcw size={12} />
            New thread
          </button>
        </div>

        {summaryText && (
          <div className="mt-4 rounded-2xl border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
            <span className="font-medium text-foreground">Thread summary:</span> {summaryText}
          </div>
        )}

        {promptActions.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {promptActions.map((action) => (
              <button
                key={action.id}
                type="button"
                className="inline-flex items-center gap-2 rounded-full border border-border bg-background px-3 py-2 text-xs font-medium text-muted-foreground transition hover:border-foreground/20 hover:text-foreground"
                onClick={() => onSubmit(action.prompt)}
                disabled={isStreaming}
              >
                <WandSparkles size={12} />
                {action.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-3 border-b border-destructive/20 bg-destructive/10 px-6 py-3 text-sm text-destructive">
          <span className="flex-1">{error}</span>
          <button className="underline" onClick={onDismissError}>Dismiss</button>
        </div>
      )}

      {isHydrating && (
        <div className="border-b border-border px-6 py-3 text-sm text-muted-foreground">
          Loading the durable thread history…
        </div>
      )}

      <MessageList
        messages={messages}
        streamingContent={streamingContent}
        isStreaming={isStreaming}
        emptyTitle="Start a workflow in chat"
        emptyBody="Use the setup context from the left rail, then ask for account search, account research, or contact search."
      />

      <ChatInput
        onSubmit={onSubmit}
        isStreaming={isStreaming}
        placeholder={isStreaming ? 'Waiting for the current turn…' : 'Ask the workspace to find accounts, research an account, or find contacts'}
      />
    </div>
  )
}
