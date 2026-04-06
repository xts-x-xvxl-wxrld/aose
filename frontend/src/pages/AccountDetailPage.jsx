import React, { useContext, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  listAccounts,
  deleteAccount,
  startAccountCrawl,
  getAccountCrawlStatus,
  listAccountPageSnapshots,
  listAccountExtractedFacts,
  searchContacts,
  listContacts,
} from '../api.js'
import { AuthContext } from '../App.jsx'
import InlineConfirm from '../components/InlineConfirm.jsx'
import {
  normalizeCrawlStatus,
  buildCrawlStatus,
  hasCrawlTarget,
  accountCrawlSummary,
  accountWebsiteLabel,
  formatDateTime,
} from '../utils/crawl.js'

const CRAWL_POLL_INTERVAL_MS = 5000

function formatFactValue(value) {
  if (value == null) return 'No value'
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

function formatConfidence(value) {
  if (typeof value !== 'number') return 'n/a'
  return value.toFixed(2)
}

function snapshotPreview(snapshot) {
  return String(snapshot?.fit_markdown || snapshot?.cleaned_markdown || '').trim().slice(0, 320)
}

function snapshotReasons(snapshot) {
  const reasons = snapshot?.fetch_metadata?.classification?.reasons
  return Array.isArray(reasons) ? reasons : []
}

export default function AccountDetailPage() {
  const { token } = useContext(AuthContext)
  const { sellerId, accountId } = useParams()
  const navigate = useNavigate()

  const [account, setAccount] = useState(null)
  const [crawlState, setCrawlState] = useState(null)
  const [snapshots, setSnapshots] = useState([])
  const [facts, setFacts] = useState([])
  const [contacts, setContacts] = useState([])
  const [loadingDetails, setLoadingDetails] = useState(false)
  const [loadingAccount, setLoadingAccount] = useState(false)
  const [isFindingPeople, setIsFindingPeople] = useState(false)
  const [isStartingCrawl, setIsStartingCrawl] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isRemoving, setIsRemoving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [confirmRemove, setConfirmRemove] = useState(false)

  const crawlPollerRef = useRef(null)

  function clearPoller() {
    if (crawlPollerRef.current) {
      window.clearInterval(crawlPollerRef.current)
      crawlPollerRef.current = null
    }
  }

  function startPoller() {
    clearPoller()
    crawlPollerRef.current = window.setInterval(async () => {
      if (!token || !sellerId || !accountId) return
      try {
        const status = await getAccountCrawlStatus(token, sellerId, accountId)
        setCrawlState((prev) => ({
          ...buildCrawlStatus(account, prev || {}),
          ...status,
          crawl_status: normalizeCrawlStatus(status.crawl_status),
        }))
        if (status.crawl_status && status.crawl_status !== 'running') {
          clearPoller()
          // Reload details after crawl finishes
          loadDetails(true)
        }
      } catch {
        clearPoller()
      }
    }, CRAWL_POLL_INTERVAL_MS)
  }

  async function loadAccount() {
    if (!token || !sellerId || !accountId) return
    setLoadingAccount(true)
    try {
      const data = await listAccounts(token, sellerId)
      const found = data.find((a) => a.id === accountId)
      setAccount(found || null)
      if (found) {
        const cs = buildCrawlStatus(found)
        setCrawlState(cs)
        if (cs.crawl_status === 'running') {
          startPoller()
        }
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingAccount(false)
    }
  }

  async function loadDetails(force = false) {
    if (!token || !sellerId || !accountId) return
    setLoadingDetails(true)
    try {
      const [snapshotData, factData, statusData, contactData] = await Promise.all([
        listAccountPageSnapshots(token, sellerId, accountId),
        listAccountExtractedFacts(token, sellerId, accountId),
        getAccountCrawlStatus(token, sellerId, accountId),
        listContacts(token, sellerId, accountId),
      ])
      setSnapshots(snapshotData)
      setFacts(factData)
      setContacts(contactData)
      setCrawlState((prev) => ({
        ...(prev || {}),
        ...statusData,
        crawl_status: normalizeCrawlStatus(statusData.crawl_status),
      }))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingDetails(false)
    }
  }

  async function handleFindPeople() {
    if (!token || !sellerId || !accountId) return
    setIsFindingPeople(true)
    setMessage('')
    setError('')
    try {
      const result = await searchContacts(token, sellerId, accountId)
      setContacts(result.contacts)
      setMessage(`Found ${result.total_returned} contact${result.total_returned === 1 ? '' : 's'}.`)
    } catch (err) {
      setError(err.message)
    } finally {
      setIsFindingPeople(false)
    }
  }

  useEffect(() => {
    if (account) {
      document.title = `${account.display_name || account.name || 'Account'} — ICP Search`
    } else {
      document.title = 'Account — ICP Search'
    }
  }, [account?.display_name, account?.name])

  useEffect(() => {
    loadAccount()
    return () => clearPoller()
  }, [token, sellerId, accountId])

  useEffect(() => {
    if (account) {
      loadDetails()
    }
  }, [account?.id])

  async function handleStartCrawl() {
    if (!token || !sellerId || !accountId || !hasCrawlTarget(account)) return
    setIsStartingCrawl(true)
    setMessage('')
    setError('')
    try {
      const status = await startAccountCrawl(token, sellerId, accountId)
      setCrawlState((prev) => ({
        ...(prev || buildCrawlStatus(account)),
        ...status,
        crawl_status: normalizeCrawlStatus(status.crawl_status),
        last_crawled_at: account.last_crawled_at || null,
        pages_saved: 0,
        facts_saved: 0,
        failed_urls: [],
      }))
      startPoller()
      await loadDetails(true)
      setMessage(`Started crawl for ${account.display_name || account.name}.`)
    } catch (err) {
      setError(err.message)
    } finally {
      setIsStartingCrawl(false)
    }
  }

  async function handleRefreshStatus() {
    if (!token || !sellerId || !accountId) return
    setIsRefreshing(true)
    setMessage('')
    setError('')
    try {
      const status = await getAccountCrawlStatus(token, sellerId, accountId)
      setCrawlState((prev) => ({
        ...(prev || {}),
        ...status,
        crawl_status: normalizeCrawlStatus(status.crawl_status),
      }))
      if (status.crawl_status === 'running') {
        startPoller()
      } else {
        clearPoller()
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setIsRefreshing(false)
    }
  }

  async function handleRefreshDetails() {
    await loadDetails(true)
  }

  async function handleRemove() {
    if (!token || !sellerId || !accountId || !account) return
    setIsRemoving(true)
    setMessage('')
    setError('')
    try {
      await deleteAccount(token, sellerId, accountId)
      clearPoller()
      navigate(`/sellers/${sellerId}/accounts`, { replace: true })
    } catch (err) {
      setError(err.message)
      setIsRemoving(false)
    }
  }

  const sortedSnapshots = [...snapshots].sort((a, b) =>
    (a.page_type || 'other').localeCompare(b.page_type || 'other')
  )

  const sortedFacts = [...facts].sort((a, b) =>
    (a.field_name || '').localeCompare(b.field_name || '')
  )

  if (loadingAccount) {
    return (
      <div className="page-stack">
        <section className="panel">
          <p className="empty">Loading account...</p>
        </section>
      </div>
    )
  }

  return (
    <div className="page-stack">
      {message && <p className="notice success" role="status">{message}</p>}
      {error && <p className="notice error" role="alert">{error}</p>}

      <section className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Account</p>
            <h2>{account ? account.display_name || account.name : 'Account page'}</h2>
          </div>
          <button
            className="ghost"
            type="button"
            onClick={() => navigate(`/sellers/${sellerId}/accounts`)}
          >
            ← Back to discovery
          </button>
        </div>

        {!sellerId ? (
          <p className="empty">Select a seller before opening an account page.</p>
        ) : !account ? (
          <p className="empty">We couldn't find that account for the current seller.</p>
        ) : (
          <div className="stack">
            <div className="account-page-hero">
              <div className="account-page-copy">
                <p>
                  {[account.locality, account.region, account.country]
                    .filter(Boolean)
                    .join(', ') || 'Location not available'}
                </p>
                <p>
                  {[
                    account.employee_count ? `${account.employee_count} employees` : '',
                    account.size,
                    account.company_type,
                  ]
                    .filter(Boolean)
                    .join(' | ') || 'Firmographics not available'}
                </p>
                <p>
                  {[account.industry, account.industry_v2].filter(Boolean).join(' / ') ||
                    'Industry not available'}
                </p>
                <p className="saved-account-meta">{accountWebsiteLabel(account)}</p>
                <p className="saved-account-meta">{accountCrawlSummary(account, crawlState)}</p>
                <p className="saved-account-meta">
                  Last crawled: {formatDateTime(crawlState?.last_crawled_at, 'Not yet crawled')}
                </p>
                {!hasCrawlTarget(account) && (
                  <p className="notice warning">
                    Add a company website before trying to crawl this account.
                  </p>
                )}
              </div>

              <div className="saved-account-actions account-page-actions">
                <button
                  className="ghost"
                  type="button"
                  disabled={isStartingCrawl || crawlState?.crawl_status === 'running' || !hasCrawlTarget(account)}
                  onClick={handleStartCrawl}
                >
                  {crawlState?.crawl_status === 'running'
                    ? 'Running...'
                    : isStartingCrawl
                      ? 'Starting...'
                      : crawlState?.crawl_status === 'completed'
                        ? 'Re-crawl'
                        : 'Start crawl'}
                </button>
                <button
                  className="ghost"
                  type="button"
                  disabled={isRefreshing || loadingDetails}
                  onClick={() => { handleRefreshStatus(); handleRefreshDetails() }}
                >
                  {(isRefreshing || loadingDetails) ? 'Refreshing...' : 'Refresh'}
                </button>
                <button
                  className="ghost"
                  type="button"
                  disabled={isFindingPeople}
                  onClick={handleFindPeople}
                >
                  {isFindingPeople ? 'Searching...' : 'Find people'}
                </button>
                {!confirmRemove ? (
                  <button
                    className="ghost danger"
                    type="button"
                    disabled={isRemoving}
                    onClick={() => setConfirmRemove(true)}
                  >
                    Remove account
                  </button>
                ) : (
                  <InlineConfirm
                    label="Remove?"
                    confirmLabel="Yes, remove"
                    loading={isRemoving}
                    onConfirm={handleRemove}
                    onCancel={() => setConfirmRemove(false)}
                  />
                )}
              </div>
            </div>

            <div className="stats">
              <div>
                <strong>{crawlState?.pages_saved ?? 0}</strong>
                <span>Pages saved</span>
              </div>
              <div>
                <strong>{crawlState?.facts_saved ?? 0}</strong>
                <span>Facts saved</span>
              </div>
              <div>
                <strong>{crawlState?.failed_urls?.length ?? 0}</strong>
                <span>Failed URLs</span>
              </div>
              <div>
                <strong>{contacts.length}</strong>
                <span>Contacts</span>
              </div>
            </div>

            {crawlState?.failed_urls?.length > 0 && (
              <div className="notice warning">
                <strong>Failed URLs</strong>
                <div className="result-link-row">
                  {crawlState.failed_urls.map((url) => (
                    <span key={url} className="result-tag">{url}</span>
                  ))}
                </div>
              </div>
            )}

            {/* Contacts */}
            <section className="contacts-section">
              <div className="panel-heading detail-heading">
                <h2>Contacts</h2>
                <span>{contacts.length}</span>
              </div>
              {isFindingPeople ? (
                <p className="empty">Searching for people...</p>
              ) : contacts.length === 0 ? (
                <p className="empty">No contacts yet — click &ldquo;Find people&rdquo; to search for people at this company.</p>
              ) : (
                <div className="contact-grid">
                  {contacts.map((contact) => (
                    <article key={contact.id} className="contact-card">
                      <div className="contact-card-header">
                        <div>
                          <h3>{contact.full_name || 'Unknown'}</h3>
                          <p className="saved-account-meta">{contact.job_title || 'No title'}</p>
                        </div>
                        <div className="contact-pills">
                          {contact.seniority && (
                            <span className="status-pill status-completed">{contact.seniority}</span>
                          )}
                          {contact.department && (
                            <span className="status-pill">{contact.department}</span>
                          )}
                        </div>
                      </div>
                      <div className="contact-fields">
                        {contact.work_email && (
                          <p className="contact-field">
                            <span className="contact-label">Email</span>
                            <a href={`mailto:${contact.work_email}`}>{contact.work_email}</a>
                          </p>
                        )}
                        {contact.phone_number && (
                          <p className="contact-field">
                            <span className="contact-label">Phone</span>
                            {contact.phone_number}
                          </p>
                        )}
                        {contact.linkedin_url && (
                          <p className="contact-field">
                            <span className="contact-label">LinkedIn</span>
                            <a href={contact.linkedin_url} target="_blank" rel="noopener noreferrer">
                              {contact.linkedin_url.replace(/^https?:\/\/(www\.)?linkedin\.com\/in\//, '')}
                            </a>
                          </p>
                        )}
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>

            {/* Why this account — ICP fit rationale from ResearchAgent */}
            {(account?.fit_score != null || account?.fit_rationale) && (
              <section className="detail-section">
                <div className="panel-heading detail-heading">
                  <h2>Why this account</h2>
                  {account.fit_score != null && (
                    <span
                      className={`status-pill ${account.fit_score >= 0.7 ? 'status-completed' : account.fit_score >= 0.5 ? 'status-running' : ''}`}
                      title="ICP fit score (0–1)"
                    >
                      {(account.fit_score * 100).toFixed(0)}% fit
                    </span>
                  )}
                </div>
                {account.fit_rationale && (
                  <p className="result-summary">{account.fit_rationale}</p>
                )}
                {facts.length > 0 && (
                  <div className="detail-card-grid">
                    {facts.slice(0, 3).map((fact) => (
                      <article key={fact.id} className="detail-card">
                        <div className="detail-card-header">
                          <h3 className="detail-card-title">{fact.field_name}</h3>
                          <span className="status-pill status-completed">
                            {typeof fact.confidence === 'number' ? fact.confidence.toFixed(2) : 'n/a'}
                          </span>
                        </div>
                        <p className="detail-fact-value">{formatFactValue(fact.value_json)}</p>
                      </article>
                    ))}
                  </div>
                )}
              </section>
            )}

            {loadingDetails ? (
              <p className="empty">Loading account details...</p>
            ) : (
              <div className="detail-sections">
                {/* Page Snapshots */}
                <section className="detail-section">
                  <div className="panel-heading detail-heading">
                    <h2>Crawled pages</h2>
                    <span>{snapshots.length}</span>
                  </div>
                  {sortedSnapshots.length === 0 ? (
                    <p className="empty">No pages crawled yet — start a crawl to capture this company&rsquo;s website.</p>
                  ) : (
                    <div className="detail-card-grid">
                      {sortedSnapshots.map((snapshot) => (
                        <article key={snapshot.id} className="detail-card">
                          <div className="detail-card-header">
                            <div className="detail-card-title">
                              <h3>{snapshot.title || snapshot.page_type || 'Untitled page'}</h3>
                              <p className="saved-account-meta detail-url">{snapshot.url}</p>
                            </div>
                            <span className={`status-pill detail-pill status-${snapshot.page_type || 'other'}`}>
                              {snapshot.page_type || 'other'}
                            </span>
                          </div>
                          <p className="saved-account-meta">
                            HTTP {snapshot.http_status ?? 'n/a'} · JS {snapshot.fetch_metadata?.used_js ? 'yes' : 'no'} · {formatDateTime(snapshot.captured_at)}
                          </p>
                          {snapshotPreview(snapshot) && (
                            <p className="result-summary detail-preview">{snapshotPreview(snapshot)}</p>
                          )}
                          {snapshotReasons(snapshot).length > 0 && (
                            <div className="result-tag-list">
                              {snapshotReasons(snapshot).map((reason) => (
                                <span key={`${snapshot.id}-${reason}`} className="result-tag">{reason}</span>
                              ))}
                            </div>
                          )}
                        </article>
                      ))}
                    </div>
                  )}
                </section>

                {/* Extracted Facts */}
                <section className="detail-section">
                  <div className="panel-heading detail-heading">
                    <h2>Extracted facts</h2>
                    <span>{facts.length}</span>
                  </div>
                  {sortedFacts.length === 0 ? (
                    <p className="empty">No signals extracted yet — crawl this account to surface company facts.</p>
                  ) : (
                    <div className="detail-card-grid">
                      {sortedFacts.map((fact) => (
                        <article key={fact.id} className="detail-card">
                          <div className="detail-card-header">
                            <div className="detail-card-title">
                              <h3>{fact.field_name}</h3>
                              <p className="saved-account-meta detail-url">{fact.source_url}</p>
                            </div>
                            <span className="status-pill status-completed">
                              {formatConfidence(fact.confidence)}
                            </span>
                          </div>
                          <p className="detail-fact-value">{formatFactValue(fact.value_json)}</p>
                          {fact.snippet && <p className="result-summary detail-preview">{fact.snippet}</p>}
                          <p className="saved-account-meta">
                            {fact.extraction_method || 'deterministic extractor'} · {formatDateTime(fact.observed_at)}
                          </p>
                        </article>
                      ))}
                    </div>
                  )}
                </section>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  )
}
