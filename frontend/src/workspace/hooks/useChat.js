import { useCallback } from 'react'

import { chat as chatApi } from '@/lib/api'
import { streamChat } from '@/lib/sse'
import { useAuthStore } from '@/stores/authStore'
import { useChatStore } from '@/stores/chatStore'
import { useTenantStore } from '@/stores/tenantStore'

function buildRequestId() {
  return `chat-${crypto.randomUUID()}`
}

export function useChat() {
  const token = useAuthStore((state) => state.token)
  const activeTenantId = useTenantStore((state) => state.activeTenantId)
  const getTenantContext = useTenantStore((state) => state.getTenantContext)
  const updateTenantContext = useTenantStore((state) => state.updateTenantContext)

  const messages = useChatStore((state) => state.messages)
  const metaEvents = useChatStore((state) => state.metaEvents)
  const threadId = useChatStore((state) => state.threadId)
  const activeWorkflow = useChatStore((state) => state.activeWorkflow)
  const summaryText = useChatStore((state) => state.summaryText)
  const isHydrating = useChatStore((state) => state.isHydrating)
  const isStreaming = useChatStore((state) => state.isStreaming)
  const streamingContent = useChatStore((state) => state.streamingContent)
  const error = useChatStore((state) => state.error)

  const setTenantSession = useChatStore((state) => state.setTenantSession)
  const startHydrating = useChatStore((state) => state.startHydrating)
  const finishHydrating = useChatStore((state) => state.finishHydrating)
  const hydrateThreadState = useChatStore((state) => state.hydrateThreadState)
  const appendOptimisticUserMessage = useChatStore((state) => state.appendOptimisticUserMessage)
  const startStreaming = useChatStore((state) => state.startStreaming)
  const appendStreamText = useChatStore((state) => state.appendStreamText)
  const setThreadId = useChatStore((state) => state.setThreadId)
  const appendMetaEvent = useChatStore((state) => state.appendMetaEvent)
  const setMetaEvents = useChatStore((state) => state.setMetaEvents)
  const finishStreamingFallback = useChatStore((state) => state.finishStreamingFallback)
  const setError = useChatStore((state) => state.setError)
  const clearError = useChatStore((state) => state.clearError)
  const clearThreadState = useChatStore((state) => state.clearThreadState)

  const refreshThreadState = useCallback(async ({ tenantId = activeTenantId, threadId: targetThreadId = '' } = {}) => {
    if (!token || !tenantId || !targetThreadId) {
      clearThreadState()
      return
    }

    startHydrating()
    try {
      const [thread, messageResponse, eventResponse] = await Promise.all([
        chatApi.getThread(token, tenantId, targetThreadId),
        chatApi.listMessages(token, tenantId, targetThreadId),
        chatApi.listEvents(token, tenantId, { threadId: targetThreadId, limit: 50 }),
      ])

      hydrateThreadState({
        thread,
        messages: messageResponse.messages,
        events: eventResponse.events,
      })
    } catch (err) {
      setError(err.message || 'Unable to load chat history.')
    } finally {
      finishHydrating()
    }
  }, [
    activeTenantId,
    clearThreadState,
    finishHydrating,
    hydrateThreadState,
    setError,
    startHydrating,
    token,
  ])

  const submit = useCallback(async (userMessage) => {
    const trimmedMessage = userMessage.trim()
    if (!token || !activeTenantId || !trimmedMessage || isStreaming) return

    const tenantContext = getTenantContext(activeTenantId)
    const requestId = buildRequestId()

    clearError()
    appendOptimisticUserMessage(trimmedMessage)
    startStreaming()

    let nextThreadId = tenantContext.threadId || threadId || ''

    try {
      for await (const event of streamChat({
        token,
        tenantId: activeTenantId,
        requestId,
        payload: {
          user_message: trimmedMessage,
          thread_id: nextThreadId || undefined,
          seller_profile_id: tenantContext.activeSellerProfileId || undefined,
          icp_profile_id: tenantContext.activeIcpProfileId || undefined,
          selected_account_id: tenantContext.activeAccountId || undefined,
          selected_contact_id: tenantContext.activeContactId || undefined,
          active_workflow: activeWorkflow || undefined,
        },
      })) {
        if (event.type === 'text') {
          if (event.threadId) {
            nextThreadId = event.threadId
            setThreadId(event.threadId)
            updateTenantContext(activeTenantId, { threadId: event.threadId })
          }
          appendStreamText(event.text)
        }

        if (event.type === 'meta') {
          appendMetaEvent(event.meta)
        }
      }

      if (nextThreadId) {
        await refreshThreadState({ tenantId: activeTenantId, threadId: nextThreadId })
      } else {
        finishStreamingFallback()
      }
    } catch (err) {
      setError(err.message || 'Unable to send chat turn.')
    }
  }, [
    activeTenantId,
    activeWorkflow,
    appendMetaEvent,
    appendOptimisticUserMessage,
    appendStreamText,
    clearError,
    finishStreamingFallback,
    getTenantContext,
    isStreaming,
    refreshThreadState,
    setError,
    setThreadId,
    startStreaming,
    threadId,
    token,
    updateTenantContext,
  ])

  const initializeTenantSession = useCallback(async (tenantId) => {
    setTenantSession(tenantId)
    const tenantContext = getTenantContext(tenantId)
    if (tenantContext.threadId) {
      await refreshThreadState({ tenantId, threadId: tenantContext.threadId })
    } else {
      clearThreadState()
    }
  }, [
    clearThreadState,
    getTenantContext,
    refreshThreadState,
    setTenantSession,
  ])

  const refreshEvents = useCallback(async () => {
    if (!token || !activeTenantId || !threadId) return
    try {
      const response = await chatApi.listEvents(token, activeTenantId, {
        threadId,
        limit: 50,
      })
      setMetaEvents(response.events)
    } catch {
      // Best-effort refresh only.
    }
  }, [activeTenantId, setMetaEvents, threadId, token])

  return {
    messages,
    metaEvents,
    threadId,
    activeWorkflow,
    summaryText,
    isHydrating,
    isStreaming,
    streamingContent,
    error,
    submit,
    refreshEvents,
    refreshThreadState,
    initializeTenantSession,
  }
}
