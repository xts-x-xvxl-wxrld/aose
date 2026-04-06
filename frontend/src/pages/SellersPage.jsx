import React, { useContext, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listSellers, createSeller, updateSeller, deleteSeller } from '../api.js'
import { AuthContext } from '../App.jsx'
import InlineConfirm from '../components/InlineConfirm.jsx'

export default function SellersPage() {
  const { token } = useContext(AuthContext)
  const navigate = useNavigate()

  const [sellers, setSellers] = useState([])
  const [selectedSellerId, setSelectedSellerId] = useState('')
  const [newSellerName, setNewSellerName] = useState('')
  const [renameName, setRenameName] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)

  useEffect(() => { document.title = 'Sellers — ICP Search' }, [])

  const selectedSeller = sellers.find((s) => s.id === selectedSellerId) || null

  async function loadSellers() {
    if (!token) return
    setLoading(true)
    try {
      const data = await listSellers(token)
      setSellers(data)
      if (data.length > 0 && !data.some((s) => s.id === selectedSellerId)) {
        setSelectedSellerId(data[0].id)
        setRenameName(data[0].name)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadSellers()
  }, [token])

  useEffect(() => {
    if (selectedSeller) {
      setRenameName(selectedSeller.name)
    }
  }, [selectedSellerId])

  async function handleCreate(e) {
    e.preventDefault()
    if (!newSellerName.trim()) return
    setLoading(true)
    setMessage('')
    setError('')
    try {
      const seller = await createSeller(token, newSellerName.trim())
      setNewSellerName('')
      setConfirmDelete(false)
      await loadSellers()
      setSelectedSellerId(seller.id)
      setRenameName(seller.name)
      setMessage('Seller created.')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleRename(e) {
    e.preventDefault()
    if (!selectedSeller || !renameName.trim()) return
    setLoading(true)
    setMessage('')
    setError('')
    try {
      await updateSeller(token, selectedSeller.id, renameName.trim())
      await loadSellers()
      setMessage('Seller updated.')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleDelete() {
    if (!selectedSeller) return
    setLoading(true)
    setMessage('')
    setError('')
    try {
      await deleteSeller(token, selectedSeller.id)
      setConfirmDelete(false)
      await loadSellers()
      setMessage('Seller deleted.')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function handleSelectSeller(sellerId) {
    setSelectedSellerId(sellerId)
    const s = sellers.find((x) => x.id === sellerId)
    setRenameName(s?.name || '')
  }

  return (
    <div className="page-stack">
      {message && <p className="notice success" role="status">{message}</p>}
      {error && <p className="notice error" role="alert">{error}</p>}

      <div className="page-grid">
        <section className="panel">
          <div className="panel-heading">
            <h2>Sellers</h2>
            <span>{sellers.length} sellers</span>
          </div>

          <form className="stack" onSubmit={handleCreate}>
            <label>
              <span>New seller</span>
              <input
                type="text"
                placeholder="Acme outbound team"
                value={newSellerName}
                onChange={(e) => setNewSellerName(e.target.value)}
              />
            </label>
            <button type="submit" disabled={loading || !newSellerName.trim()}>
              Create seller
            </button>
          </form>

          {sellers.length > 0 && (
            <div className="stack" style={{ marginTop: '1rem' }}>
              <form onSubmit={handleRename}>
                <label>
                  <span>Rename</span>
                  <input
                    type="text"
                    value={renameName}
                    onChange={(e) => setRenameName(e.target.value)}
                  />
                </label>
                <div className="inline-actions" style={{ marginTop: '0.75rem' }}>
                  <button type="submit" disabled={loading || !selectedSeller}>
                    Save name
                  </button>
                  {!confirmDelete ? (
                    <button
                      className="ghost danger"
                      type="button"
                      disabled={loading || !selectedSeller}
                      onClick={() => setConfirmDelete(true)}
                    >
                      Delete seller
                    </button>
                  ) : (
                    <InlineConfirm
                      label={`Delete "${selectedSeller?.name}"?`}
                      confirmLabel="Yes, delete"
                      loading={loading}
                      onConfirm={handleDelete}
                      onCancel={() => setConfirmDelete(false)}
                    />
                  )}
                </div>
              </form>
            </div>
          )}
        </section>

        <section className="panel">
          <div className="panel-heading">
            <h2>Your workspaces</h2>
            <span>{selectedSeller?.name || 'None selected'}</span>
          </div>

          {sellers.length > 0 ? (
            <div className="seller-list">
              {sellers.map((seller) => (
                <button
                  key={seller.id}
                  type="button"
                  className={`seller-card${seller.id === selectedSellerId ? ' active' : ''}`}
                  onClick={() => {
                    handleSelectSeller(seller.id)
                    navigate(`/sellers/${seller.id}/icps`)
                  }}
                >
                  <strong title={seller.name}>{seller.name}</strong>
                  <span>{new Date(seller.created_at || seller.updated_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) || ''}</span>
                </button>
              ))}
            </div>
          ) : (
            <p className="empty">No workspaces yet — create one above to get started.</p>
          )}
        </section>
      </div>
    </div>
  )
}
