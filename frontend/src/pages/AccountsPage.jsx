import React, { useCallback, useContext, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  listIcps,
  listAccounts,
  createAccount,
  deleteAccount,
  runCompanySearch,
  startAccountCrawl,
  getAccountCrawlStatus,
} from '../api.js'
import { AuthContext } from '../App.jsx'
import {
  normalizeCrawlStatus,
  buildCrawlStatus,
  hasCrawlTarget,
  accountCrawlSummary,
  accountWebsiteLabel,
  crawlStatusLabel,
  crawlStatusClass,
  formatDateTime,
} from '../utils/crawl.js'

const CRAWL_POLL_INTERVAL_MS = 5000

function toCompanyDisplay(company) {
  return {
    raw: company,
    title: company.display_name || company.name || 'Unnamed company',
    locationLabel:
      [company.location?.locality, company.location?.region, company.location?.country]
        .map((v) => String(v || '').trim())
        .filter(Boolean)
        .join(', ') || 'Location not available',
    websiteLabel: company.website || company.display_name || 'No website listed',
    firmographicLabel:
      [company.employee_count ? `${company.employee_count} employees` : '', company.size, company.type]
        .filter(Boolean)
        .join(' | ') || 'Firmographics not available',
    industryLabel: [company.industry, company.industry_v2].filter(Boolean).join(' / ') || 'Industry not available',
    headline: company.headline || '',
    summaryPreview: String(company.summary || '').trim().slice(0, 220),
  }
}

export default function AccountsPage() {
  const { token } = useContext(AuthContext)
  const { sellerId } = useParams()
  const navigate = useNavigate()

  const [icps, setIcps] = useState([])
  const [activeIcpId, setActiveIcpId] = useState('')
  const [accounts, setAccounts] = useState([])
  const [crawlStatusByAccountId, setCrawlStatusByAccountId] = useState({})
  const [searchSize, setSearchSize] = useState(10)
  const [searchPretty, setSearchPretty] = useState(true)
  const [searchResult, setSearchResult] = useState(null)
  const [savingAccountIds, setSavingAccountIds] = useState([])
  const [removingAccountIds, setRemovingAccountIds] = useState([])
  const [crawlingAccountIds, setCrawlingAccountIds] = useState([])
  const [refreshingAccountIds, setRefreshingAccountIds] = useState([])
  const [runningSearch, setRunningSearch] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const crawlPollersRef = useRef(new Map())

  const savedAccountSourceIds = new Set(accounts.map((a) => `${a.source}:${a.source_record_id}`))
  const canRunDiscovery = Boolean(sellerId && activeIcpId)
  const canLoadMore = Boolean(searchResult?.scroll_token)
  const activeIcp = icps.find((icp) => icp.id === activeIcpId) || null

  function getAccountCrawlState(account) {
    return crawlStatusByAccountId[account.id] || buildCrawlStatus(account)
  }

  function applyCrawlStatus(accountId, payload) {
    setCrawlStatusByAccountId((prev) => {
      const existingAccount = accounts.find((a) => a.id === accountId)
      const previous = prev[accountId] || {}
      return {
        ...prev,
        [accountId]: {
          account_id: accountId,
          crawl_status: normalizeCrawlStatus(payload?.crawl_status ?? existingAccount?.crawl_status ?? previous.crawl_status),
          last_crawled_at: payload?.last_crawled_at ?? existingAccount?.last_crawled_at ?? previous.last_crawled_at ?? null,
          pages_saved: Number(payload?.pages_saved ?? previous.pages_saved ?? 0),
          facts_saved: Number(payload?.facts_saved ?? previous.facts_saved ?? 0),
          failed_urls: Array.isArray(payload?.failed_urls) ? payload.failed_urls : previous.failed_urls || [],
        },
      }
    })
  }

  function clearCrawlPolling(accountId) {
    const intervalId = crawlPollersRef.current.get(accountId)
    if (intervalId) {
      window.clearInterval(intervalId)
      crawlPollersRef.current.delete(accountId)
    }
  }

  function stopAllCrawlPolling() {
    for (const intervalId of crawlPollersRef.current.values()) {
      window.clearInterval(intervalId)
    }
    crawlPollersRef.current.clear()
  }

  async function refreshAccountStatusSilent(accountId) {
    if (!token || !sellerId || !accountId) return null
    try {
      const status = await getAccountCrawlStatus(token, sellerId, accountId)
      applyCrawlStatus(accountId, status)
      return status
    } catch {
      return null
    }
  }

  function ensureCrawlPolling(accountId) {
    if (crawlPollersRef.current.has(accountId)) return
    const intervalId = window.setInterval(async () => {
      const status = await refreshAccountStatusSilent(accountId)
      if (status && status.crawl_status && status.crawl_status !== 'running') {
        clearCrawlPolling(accountId)
        // Reload accounts after crawl finishes
        loadAccounts()
      }
    }, CRAWL_POLL_INTERVAL_MS)
    crawlPollersRef.current.set(accountId, intervalId)
  }

  async function loadAccounts() {
    if (!token || !sellerId) return
    try {
      const data = await listAccounts(token, sellerId)
      setAccounts(data)
      const nextStatuses = {}
      for (const account of data) {
        nextStatuses[account.id] = buildCrawlStatus(account, crawlStatusByAccountId[account.id] || {})
      }
      setCrawlStatusByAccountId(nextStatuses)
      // Start polling for running accounts
      for (const account of data) {
        const status = normalizeCrawlStatus(account.crawl_status)
        if (status === 'running') {
          ensureCrawlPolling(account.id)
        }
      }
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => { document.title = 'Account Discovery — ICP Search' }, [])

  useEffect(() => {
    if (!token || !sellerId) return
    setLoading(true)
    Promise.all([
      listIcps(token, sellerId),
      listAccounts(token, sellerId),
    ])
      .then(([icpData, accountData]) => {
        setIcps(icpData)
        setAccounts(accountData)
        if (icpData.length > 0) setActiveIcpId(icpData[0].id)
        const nextStatuses = {}
        for (const account of accountData) {
          nextStatuses[account.id] = buildCrawlStatus(account)
        }
        setCrawlStatusByAccountId(nextStatuses)
        for (const account of accountData) {
          if (normalizeCrawlStatus(account.crawl_status) === 'running') {
            ensureCrawlPolling(account.id)
          }
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))

    return () => stopAllCrawlPolling()
  }, [token, sellerId])

  async function handleSearch(loadMore = false) {
    if (!canRunDiscovery) return
    if (loadMore) {
      setLoadingMore(true)
    } else {
      setRunningSearch(true)
      setSearchResult(null)
    }
    setMessage('')
    setError('')
    try {
      const response = await runCompanySearch(token, sellerId, activeIcpId, {
        size: Number(searchSize) || 10,
        pretty: searchPretty,
        scroll_token: loadMore ? searchResult?.scroll_token || null : null,
      })
      if (loadMore && searchResult) {
        setSearchResult({ ...response, data: [...searchResult.data, ...response.data] })
        setMessage('Loaded more companies.')
      } else {
        setSearchResult(response)
        setMessage('Company search complete.')
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setRunningSearch(false)
      setLoadingMore(false)
    }
  }

  async function handleSaveCompany(company) {
    if (!token || !sellerId || !company?.raw?.id) return
    setSavingAccountIds((prev) => [...prev, company.raw.id])
    setMessage('')
    setError('')
    try {
      await createAccount(token, sellerId, {
        icp_object_id: activeIcpId || null,
        source: 'pdl',
        source_record_id: company.raw.id,
        source_dataset_version: company.raw.dataset_version || null,
        company_payload: company.raw,
        request_context: {
          icp_name: activeIcp?.name || null,
          request_body: searchResult?.request_body || null,
          query: searchResult?.query || null,
        },
      })
      await loadAccounts()
      setMessage(`Saved ${company.title} to accounts.`)
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingAccountIds((prev) => prev.filter((id) => id !== company.raw.id))
    }
  }

  async function handleRemoveAccount(account) {
    if (!token || !sellerId) return
    setRemovingAccountIds((prev) => [...prev, account.id])
    setMessage('')
    setError('')
    try {
      await deleteAccount(token, sellerId, account.id)
      clearCrawlPolling(account.id)
      await loadAccounts()
      setMessage(`Removed ${account.display_name || account.name} from accounts.`)
    } catch (err) {
      setError(err.message)
    } finally {
      setRemovingAccountIds((prev) => prev.filter((id) => id !== account.id))
    }
  }

  async function handleStartCrawl(account) {
    if (!token || !sellerId || !account?.id || !hasCrawlTarget(account)) return
    setCrawlingAccountIds((prev) => [...prev, account.id])
    setMessage('')
    setError('')
    try {
      const status = await startAccountCrawl(token, sellerId, account.id)
      applyCrawlStatus(account.id, {
        ...status,
        last_crawled_at: account.last_crawled_at || null,
        pages_saved: 0,
        facts_saved: 0,
        failed_urls: [],
      })
      ensureCrawlPolling(account.id)
      setMessage(`Started crawl for ${account.display_name || account.name}.`)
    } catch (err) {
      setError(err.message)
    } finally {
      setCrawlingAccountIds((prev) => prev.filter((id) => id !== account.id))
    }
  }

  async function handleRefreshStatus(account) {
    if (!token || !sellerId || !account?.id) return
    setRefreshingAccountIds((prev) => [...prev, account.id])
    setMessage('')
    setError('')
    try {
      const status = await getAccountCrawlStatus(token, sellerId, account.id)
      applyCrawlStatus(account.id, status)
      if (status.crawl_status === 'running') {
        ensureCrawlPolling(account.id)
      } else {
        clearCrawlPolling(account.id)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setRefreshingAccountIds((prev) => prev.filter((id) => id !== account.id))
    }
  }

  const displayCompanies = (searchResult?.data || []).map(toCompanyDisplay)

  return (
    <div className="page-stack">
      {message && <p className="notice success" role="status">{message}</p>}
      {error && <p className="notice error" role="alert">{error}</p>}

      <section className="panel">
        <div className="panel-heading">
          <h2>Account discovery</h2>
          {activeIcpId && (
            <button
              className="ghost"
              type="button"
              onClick={() => navigate(`/sellers/${sellerId}/icps/${activeIcpId}/edit`)}
            >
              Edit selected ICP
            </button>
          )}
        </div>

        {!sellerId ? (
          <p className="empty">Select a workspace before searching for accounts.</p>
        ) : icps.length === 0 && !loading ? (
          <p className="empty">Create an ICP first — discovery uses your ICP criteria to find matching companies.</p>
        ) : (
          <div className="stack">
            <div className="search-bar">
              <label>
                <span>ICP</span>
                <select
                  value={activeIcpId}
                  onChange={(e) => setActiveIcpId(e.target.value)}
                >
                  {icps.map((icp) => (
                    <option key={icp.id} value={icp.id}>{icp.name}</option>
                  ))}
                </select>
              </label>
              <label>
                <span>Results per batch</span>
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={searchSize}
                  onChange={(e) => setSearchSize(e.target.value)}
                />
              </label>
              <button
                type="button"
                disabled={runningSearch || !canRunDiscovery}
                onClick={() => handleSearch(false)}
              >
                {runningSearch ? 'Searching...' : 'Search accounts'}
              </button>
              <button
                className="ghost"
                type="button"
                disabled={loadingMore || !canLoadMore}
                onClick={() => handleSearch(true)}
              >
                {loadingMore ? 'Loading...' : 'Load more'}
              </button>
            </div>

            {/* Found accounts results */}
            <section className="panel">
              <div className="panel-heading">
                <h2>Found accounts</h2>
                {searchResult && <span>{searchResult.data.length} loaded</span>}
              </div>

              {!searchResult ? (
                <p className="empty">Search above to find companies matching your ICP criteria.</p>
              ) : (
                <div className="results">
                  <div className="stats">
                    <div>
                      <strong>{searchResult.count}</strong>
                      <span>This batch</span>
                    </div>
                    <div>
                      <strong>{searchResult.data.length}</strong>
                      <span>Loaded</span>
                    </div>
                    <div>
                      <strong>{searchResult.total ?? 'n/a'}</strong>
                      <span>Total</span>
                    </div>
                  </div>

                  <div className="result-grid">
                    {displayCompanies.map((company) => {
                      const isSaved = savedAccountSourceIds.has(`pdl:${company.raw.id}`)
                      const isSaving = savingAccountIds.includes(company.raw.id)
                      return (
                        <article
                          key={company.raw.id || company.raw.website || company.raw.name}
                          className="result-card"
                        >
                          <div className="result-card-header">
                            <div>
                              <p className="result-card-eyebrow">{company.locationLabel}</p>
                              <h3>{company.title}</h3>
                            </div>
                            <p className="result-card-site">{company.websiteLabel}</p>
                          </div>
                          <div className="result-card-meta">
                            <p>{company.firmographicLabel}</p>
                            <p>{company.industryLabel}</p>
                          </div>
                          <div className="result-card-actions">
                            <button
                              className="ghost"
                              type="button"
                              disabled={isSaving || isSaved}
                              onClick={() => handleSaveCompany(company)}
                            >
                              {isSaved ? 'Saved' : isSaving ? 'Saving...' : 'Save account'}
                            </button>
                          </div>
                          {company.headline && <p className="result-headline">{company.headline}</p>}
                          {company.summaryPreview && <p className="result-summary">{company.summaryPreview}</p>}
                        </article>
                      )
                    })}
                  </div>
                </div>
              )}
            </section>

            {/* Saved accounts */}
            <section className="panel">
              <div className="panel-heading">
                <h2>Saved accounts</h2>
                <span>{accounts.length} saved</span>
              </div>

              {accounts.length > 0 ? (
                <div className="saved-account-list">
                  {accounts.map((account) => {
                    const crawlState = getAccountCrawlState(account)
                    const isStarting = crawlingAccountIds.includes(account.id)
                    const isRefreshing = refreshingAccountIds.includes(account.id)
                    const isRemoving = removingAccountIds.includes(account.id)
                    return (
                      <article key={account.id} className="saved-account-card">
                        <div className="saved-account-copy">
                          <div className="saved-account-header">
                            <div>
                              <div className="saved-account-title-row">
                                <h3>{account.display_name || account.name}</h3>
                                <span className={`status-pill ${crawlStatusClass(crawlState)}`}>
                                  {crawlStatusLabel(crawlState)}
                                </span>
                              </div>
                              <p>
                                {[account.locality, account.region, account.country]
                                  .filter(Boolean)
                                  .join(', ') || 'Location not available'}
                              </p>
                            </div>
                            <div className="saved-account-actions">
                              <button
                                className="ghost"
                                type="button"
                                disabled={isStarting || crawlState.crawl_status === 'running' || !hasCrawlTarget(account)}
                                onClick={() => handleStartCrawl(account)}
                              >
                                {crawlState.crawl_status === 'running'
                                  ? 'Running...'
                                  : isStarting
                                    ? 'Starting...'
                                    : crawlState.crawl_status === 'completed'
                                      ? 'Re-crawl'
                                      : 'Start crawl'}
                              </button>
                              <button
                                className="ghost"
                                type="button"
                                disabled={isRefreshing}
                                onClick={() => handleRefreshStatus(account)}
                              >
                                {isRefreshing ? 'Refreshing...' : 'Refresh crawl'}
                              </button>
                              <button
                                className="ghost"
                                type="button"
                                onClick={() => navigate(`/sellers/${sellerId}/accounts/${account.id}`)}
                              >
                                View account
                              </button>
                              <button
                                className="ghost danger"
                                type="button"
                                disabled={isRemoving}
                                onClick={() => handleRemoveAccount(account)}
                              >
                                {isRemoving ? 'Removing...' : 'Remove'}
                              </button>
                            </div>
                          </div>
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
                            Last crawled: {formatDateTime(crawlState.last_crawled_at, 'Not yet crawled')}
                          </p>
                          {!hasCrawlTarget(account) && (
                            <p className="notice warning">
                              Add a company website before trying to crawl this account.
                            </p>
                          )}
                        </div>
                      </article>
                    )
                  })}
                </div>
              ) : (
                <p className="empty">No saved accounts yet. Save promising discovery results here.</p>
              )}
            </section>
          </div>
        )}
      </section>
    </div>
  )
}
