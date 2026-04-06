import { create } from 'zustand'

/**
 * uiStore — panel and view state.
 *
 * mainMode drives which view is shown in the main window and whether
 * the right sidebar is visible:
 *   'chat'          → full chat window, right sidebar hidden
 *   'object-viewer' → object viewer, right sidebar visible
 */
export const useUIStore = create((set) => ({
  mainMode: 'chat',
  leftSidebarOpen: true,

  // Object viewer navigation state
  activeSellerId: null,
  activeObjectType: null, // 'icps' | 'accounts' | 'contacts' | null
  activeRecordId: null,
  objectViewerDepth: 'sellers-table', // 'sellers-table' | 'seller-overview' | 'object-table' | 'record-detail'

  // ── Actions ──────────────────────────────────────────────────────────────

  openChat: () => set({ mainMode: 'chat' }),

  toggleLeftSidebar: () => set((s) => ({ leftSidebarOpen: !s.leftSidebarOpen })),

  openSeller: (sellerId) =>
    set({
      mainMode: 'object-viewer',
      activeSellerId: sellerId,
      activeObjectType: null,
      activeRecordId: null,
      objectViewerDepth: sellerId ? 'seller-overview' : 'sellers-table',
    }),

  openObjectType: (objectType) =>
    set({
      activeObjectType: objectType,
      activeRecordId: null,
      objectViewerDepth: 'object-table',
    }),

  openRecord: (recordId) =>
    set({
      activeRecordId: recordId,
      objectViewerDepth: 'record-detail',
    }),

  navigateBack: () =>
    set((s) => {
      if (s.objectViewerDepth === 'record-detail') {
        return { activeRecordId: null, objectViewerDepth: 'object-table' }
      }
      if (s.objectViewerDepth === 'object-table') {
        return { activeObjectType: null, objectViewerDepth: 'seller-overview' }
      }
      if (s.objectViewerDepth === 'seller-overview') {
        return { activeSellerId: null, objectViewerDepth: 'sellers-table' }
      }
      return {}
    }),
}))

// Derived selector — avoids storing redundant boolean
export const selectRightSidebarOpen = (s) => s.mainMode === 'object-viewer'
