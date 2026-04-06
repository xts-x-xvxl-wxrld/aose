import React, { useState } from 'react'
import { useAuthStore } from '@/stores/authStore'
import { useUIStore } from '@/stores/uiStore'
import { sellers as sellersApi } from '@/lib/api'
import Dialog, { Field, Input, SubmitButton } from '@/workspace/actions/dialogs/Dialog'

/**
 * AddSellerDialog — creates a new Seller and immediately opens it.
 */
export default function AddSellerDialog({ open, onClose }) {
  const token      = useAuthStore((s) => s.token)
  const openSeller = useUIStore((s) => s.openSeller)

  const [name,    setName]    = useState('')
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    if (!name.trim() || loading) return
    setLoading(true)
    setError('')
    try {
      const seller = await sellersApi.create(token, name.trim())
      onClose()
      setName('')
      openSeller(seller.id)
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
      title="Add Seller"
      description="Create a new seller profile."
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Field label="Seller name">
          <Input
            autoFocus
            placeholder="e.g. Acme Corp"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={loading}
          />
        </Field>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <SubmitButton loading={loading}>Create Seller</SubmitButton>
      </form>
    </Dialog>
  )
}
