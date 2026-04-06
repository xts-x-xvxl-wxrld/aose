import React from 'react'

export default function InlineConfirm({ label, confirmLabel = 'Yes', loading = false, onConfirm, onCancel }) {
  return (
    <span className="inline-confirm">
      <span className="inline-confirm-label">{label}</span>
      <button
        type="button"
        className="danger"
        disabled={loading}
        onClick={onConfirm}
      >
        {loading ? 'Working...' : confirmLabel}
      </button>
      <button
        type="button"
        className="ghost"
        onClick={onCancel}
      >
        Cancel
      </button>
    </span>
  )
}
