import React, { useEffect, useRef } from 'react'

import { cn } from '@/lib/utils'

export default function MessageList({
  messages,
  streamingContent,
  isStreaming,
  compact = false,
  emptyTitle = 'Start a conversation',
  emptyBody = 'No messages yet.',
}) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent])

  const hasContent = messages.length > 0 || isStreaming
  if (!hasContent) {
    return (
      <div className="flex flex-1 items-center justify-center px-4">
        <div className="max-w-sm rounded-3xl border border-dashed border-border bg-muted/30 px-5 py-6 text-center">
          <p className="text-sm font-medium text-foreground">{emptyTitle}</p>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{emptyBody}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className={cn('mx-auto flex flex-col gap-3', compact ? 'p-4' : 'max-w-4xl p-6')}>
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} compact={compact} />
        ))}

        {isStreaming && (
          <MessageBubble
            compact={compact}
            message={{ role: 'assistant', content: streamingContent }}
            streaming
          />
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

function MessageBubble({ message, compact, streaming = false }) {
  const isUser = message.role === 'user'

  return (
    <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'rounded-[1.4rem] border px-4 py-3 whitespace-pre-wrap break-words shadow-sm',
          compact ? 'max-w-[92%] text-xs' : 'max-w-[78%] text-sm leading-6',
          isUser
            ? 'border-primary/10 bg-primary text-primary-foreground'
            : 'border-border bg-card text-foreground',
        )}
      >
        {message.content}
        {streaming && (
          <span className="ml-1 inline-block h-4 w-0.5 animate-pulse bg-current align-middle" />
        )}
      </div>
    </div>
  )
}
