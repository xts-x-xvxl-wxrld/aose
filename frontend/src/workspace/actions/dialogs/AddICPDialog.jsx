import React, { useState } from 'react'
import { useAuthStore } from '@/stores/authStore'
import { useUIStore } from '@/stores/uiStore'
import { icps as icpsApi } from '@/lib/api'
import Dialog, { Field, Input, Select, SubmitButton } from '@/workspace/actions/dialogs/Dialog'

/**
 * AddICPDialog — creates a minimal ICP for the active seller.
 * Name + priority only; all other spec fields default to empty and
 * can be filled by the agent or in the record detail view.
 */
export default function AddICPDialog({ open, onClose, sellerId }) {
  const token          = useAuthStore((s) => s.token)
  const openObjectType = useUIStore((s) => s.openObjectType)
  const openSeller     = useUIStore((s) => s.openSeller)

  const [name,     setName]     = useState('')
  const [priority, setPriority] = useState('1')
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    if (!name.trim() || !sellerId || loading) return
    setLoading(true)
    setError('')
    try {
      await icpsApi.create(token, sellerId, {
        name: name.trim(),
        priority: parseInt(priority, 10),
      })
      onClose()
      setName('')
      setPriority('1')
      // Navigate to the ICPs table so user sees the new record
      if (sellerId) {
        openSeller(sellerId)
        openObjectType('icps')
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={() => { onClose(); setName(''); setError('') }}
      title="Add ICP"
      description="Create a new Ideal Customer Profile for the active seller."
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Field label="ICP name">
          <Input
            autoFocus
            placeholder="e.g. Mid-market SaaS"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={loading}
          />
        </Field>
        <Field label="Priority">
          <Select
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            disabled={loading}
          >
            {[1, 2, 3, 4, 5].map((p) => (
              <option key={p} value={String(p)}>{p}</option>
            ))}
          </Select>
        </Field>
        {!sellerId && (
          <p className="text-sm text-muted-foreground">
            Open a seller first before adding an ICP.
          </p>
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}
        <SubmitButton loading={loading || !sellerId}>Create ICP</SubmitButton>
      </form>
    </Dialog>
  )
}
