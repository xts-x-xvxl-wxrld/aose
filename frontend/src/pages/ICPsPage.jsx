import React, { useContext, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { listIcps, deleteIcp } from '../api.js'
import { AuthContext } from '../App.jsx'
import InlineConfirm from '../components/InlineConfirm.jsx'

export default function ICPsPage() {
  const { token } = useContext(AuthContext)
  const { sellerId } = useParams()
  const navigate = useNavigate()

  const [icps, setIcps] = useState([])
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [confirmDeleteId, setConfirmDeleteId] = useState(null)

  useEffect(() => { document.title = 'ICPs — ICP Search' }, [])

  async function loadIcps() {
    if (!token || !sellerId) return
    setLoading(true)
    try {
      const data = await listIcps(token, sellerId)
      setIcps(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadIcps()
  }, [token, sellerId])

  async function handleDelete(icp) {
    setLoading(true)
    setMessage('')
    setError('')
    try {
      await deleteIcp(token, sellerId, icp.id)
      setConfirmDeleteId(null)
      await loadIcps()
      setMessage('ICP deleted.')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page-stack">
      {message && <p className="notice success" role="status">{message}</p>}
      {error && <p className="notice error" role="alert">{error}</p>}

      <section className="panel">
        <div className="panel-heading">
          <h2>Ideal Customer Profiles</h2>
          <button
            className="ghost"
            type="button"
            disabled={!sellerId}
            onClick={() => navigate(`/sellers/${sellerId}/icps/new`)}
          >
            New ICP
          </button>
        </div>

        {!sellerId ? (
          <p className="empty">Select a workspace before managing ICPs.</p>
        ) : loading ? (
          <p className="empty">Loading...</p>
        ) : icps.length > 0 ? (
          <div className="icp-list">
            {icps.map((icp) => (
              <article key={icp.id} className="icp-card">
                <div>
                  <strong>{icp.name}</strong>
                  <span>Priority {icp.priority}</span>
                </div>
                <div className="inline-actions">
                  <button
                    className="ghost"
                    type="button"
                    onClick={() => navigate(`/sellers/${sellerId}/icps/${icp.id}/edit`)}
                  >
                    Edit
                  </button>
                  <button
                    className="ghost"
                    type="button"
                    onClick={() => navigate(`/sellers/${sellerId}/accounts`)}
                  >
                    Use in discovery
                  </button>
                  {confirmDeleteId !== icp.id ? (
                    <button
                      className="ghost danger"
                      type="button"
                      onClick={() => setConfirmDeleteId(icp.id)}
                    >
                      Delete
                    </button>
                  ) : (
                    <InlineConfirm
                      label="Delete?"
                      loading={loading}
                      onConfirm={() => handleDelete(icp)}
                      onCancel={() => setConfirmDeleteId(null)}
                    />
                  )}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="empty">No ICPs yet — create one to start discovering target accounts.</p>
        )}
      </section>
    </div>
  )
}
