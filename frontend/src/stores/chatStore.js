import { create } from 'zustand'

function mapMessages(messages) {
  return (messages || []).map((message) => ({
    id: message.message_id || crypto.randomUUID(),
    role: message.role,
    content: message.content_text || '',
    messageType: message.message_type || 'assistant_reply',
    workflowRunId: message.workflow_run_id || null,
    createdAt: message.created_at || new Date().toISOString(),
  }))
}

export const useChatStore = create((set) => ({
  tenantId: '',
  threadId: '',
  currentRunId: '',
  activeWorkflow: '',
  summaryText: '',
  messages: [],
  metaEvents: [],
  isHydrating: false,
  isStreaming: false,
  streamingContent: '',
  error: null,

  setTenantSession: (tenantId) =>
    set((state) => ({
      tenantId,
      error: null,
      threadId: tenantId === state.tenantId ? state.threadId : '',
      currentRunId: tenantId === state.tenantId ? state.currentRunId : '',
      activeWorkflow: tenantId === state.tenantId ? state.activeWorkflow : '',
      summaryText: tenantId === state.tenantId ? state.summaryText : '',
      messages: tenantId === state.tenantId ? state.messages : [],
      metaEvents: tenantId === state.tenantId ? state.metaEvents : [],
      isHydrating: false,
      isStreaming: false,
      streamingContent: '',
    })),

  startHydrating: () => set({ isHydrating: true, error: null }),
  finishHydrating: () => set({ isHydrating: false }),

  hydrateThreadState: ({ thread, messages, events }) =>
    set({
      threadId: thread?.thread_id || '',
      currentRunId: thread?.current_run_id || '',
      activeWorkflow: thread?.active_workflow || '',
      summaryText: thread?.summary_text || '',
      messages: mapMessages(messages),
      metaEvents: events || [],
      isHydrating: false,
      isStreaming: false,
      streamingContent: '',
      error: null,
    }),

  appendOptimisticUserMessage: (content) =>
    set((state) => ({
      messages: [
        ...state.messages,
        {
          id: crypto.randomUUID(),
          role: 'user',
          content,
          messageType: 'user_turn',
          workflowRunId: null,
          createdAt: new Date().toISOString(),
        },
      ],
    })),

  startStreaming: () =>
    set({
      isStreaming: true,
      streamingContent: '',
      error: null,
    }),

  appendStreamText: (text) =>
    set((state) => ({
      streamingContent: state.streamingContent + text,
    })),

  setThreadId: (threadId) => set({ threadId }),

  setMetaEvents: (events) => set({ metaEvents: events || [] }),

  appendMetaEvent: (event) =>
    set((state) => ({
      metaEvents: [...state.metaEvents, event],
      currentRunId: event.workflow_run_id || state.currentRunId,
    })),

  finishStreamingFallback: () =>
    set((state) => ({
      messages: state.streamingContent
        ? [
            ...state.messages,
            {
              id: crypto.randomUUID(),
              role: 'assistant',
              content: state.streamingContent,
              messageType: 'assistant_reply',
              workflowRunId: state.currentRunId || null,
              createdAt: new Date().toISOString(),
            },
          ]
        : state.messages,
      isStreaming: false,
      streamingContent: '',
    })),

  setError: (error) =>
    set({
      error,
      isHydrating: false,
      isStreaming: false,
      streamingContent: '',
    }),

  clearError: () => set({ error: null }),

  clearThreadState: () =>
    set({
      threadId: '',
      currentRunId: '',
      activeWorkflow: '',
      summaryText: '',
      messages: [],
      metaEvents: [],
      isHydrating: false,
      isStreaming: false,
      streamingContent: '',
      error: null,
    }),
}))
