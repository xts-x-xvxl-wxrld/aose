import React, { useCallback, useRef, useState } from 'react'
import { Send } from 'lucide-react'

import { cn } from '@/lib/utils'

export default function ChatInput({
  onSubmit,
  isStreaming,
  compact = false,
  placeholder,
}) {
  const [value, setValue] = useState('')
  const textareaRef = useRef(null)

  const handleSubmit = useCallback(() => {
    const text = value.trim()
    if (!text || isStreaming) return
    onSubmit(text)
    setValue('')
    textareaRef.current?.focus()
  }, [isStreaming, onSubmit, value])

  const handleKeyDown = useCallback((event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      handleSubmit()
    }
  }, [handleSubmit])

  return (
    <div className={cn(
      'flex items-end gap-2 border-t border-border bg-background',
      compact ? 'px-3 py-3' : 'px-6 py-4',
    )}>
      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
        disabled={isStreaming}
        placeholder={placeholder || (isStreaming ? 'Waiting for the current turn…' : 'Message…')}
        className={cn(
          'max-h-32 flex-1 resize-none overflow-y-auto rounded-2xl border border-input bg-background px-4 py-3',
          'text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring',
          'disabled:cursor-not-allowed disabled:opacity-50',
          compact && 'text-xs',
        )}
        style={{ height: 'auto', minHeight: compact ? '2.5rem' : '3rem' }}
        onInput={(event) => {
          event.target.style.height = 'auto'
          event.target.style.height = `${Math.min(event.target.scrollHeight, 128)}px`
        }}
      />

      <button
        type="button"
        onClick={handleSubmit}
        disabled={!value.trim() || isStreaming}
        className={cn(
          'flex flex-shrink-0 items-center justify-center rounded-2xl bg-primary text-primary-foreground transition hover:bg-primary/90',
          'disabled:cursor-not-allowed disabled:opacity-40',
          compact ? 'h-10 w-10' : 'h-12 w-12',
        )}
        aria-label="Send"
      >
        <Send size={compact ? 14 : 16} />
      </button>
    </div>
  )
}
