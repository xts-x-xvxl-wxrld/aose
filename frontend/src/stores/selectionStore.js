import { create } from 'zustand'

/**
 * selectionStore — multi-select state for table rows.
 *
 * Selection is scoped to a (sellerId, objectType) context.
 * Switching seller or object type automatically clears the selection.
 */
export const useSelectionStore = create((set, get) => ({
  selectedRecords: {}, // { [recordId]: true }
  selectionObjectType: null,
  selectionSellerId: null,

  // ── Actions ──────────────────────────────────────────────────────────────

  selectRecord: (recordId, objectType, sellerId) =>
    set((s) => {
      const sameContext =
        s.selectionObjectType === objectType && s.selectionSellerId === sellerId
      return {
        selectedRecords: sameContext
          ? { ...s.selectedRecords, [recordId]: true }
          : { [recordId]: true },
        selectionObjectType: objectType,
        selectionSellerId: sellerId,
      }
    }),

  deselectRecord: (recordId) =>
    set((s) => {
      const next = { ...s.selectedRecords }
      delete next[recordId]
      return { selectedRecords: next }
    }),

  toggleRecord: (recordId, objectType, sellerId) => {
    const { selectedRecords, selectRecord, deselectRecord } = get()
    if (selectedRecords[recordId]) {
      deselectRecord(recordId)
    } else {
      selectRecord(recordId, objectType, sellerId)
    }
  },

  clearSelection: () =>
    set({ selectedRecords: {}, selectionObjectType: null, selectionSellerId: null }),

  // ── Selectors ────────────────────────────────────────────────────────────

  getSelectedIds: () => Object.keys(get().selectedRecords),
  getSelectedCount: () => Object.keys(get().selectedRecords).length,
  isSelected: (recordId) => Boolean(get().selectedRecords[recordId]),
}))
