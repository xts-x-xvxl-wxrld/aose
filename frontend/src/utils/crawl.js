export function normalizeCrawlStatus(status) {
  if (status === 'running' || status === 'completed' || status === 'failed') return status
  return 'idle'
}

export function buildCrawlStatus(account, payload = {}) {
  return {
    account_id: account?.id || payload.account_id || '',
    crawl_status: normalizeCrawlStatus(account?.crawl_status ?? payload.crawl_status),
    last_crawled_at: payload.last_crawled_at ?? account?.last_crawled_at ?? null,
    pages_saved: Number(payload.pages_saved ?? 0),
    facts_saved: Number(payload.facts_saved ?? 0),
    failed_urls: Array.isArray(payload.failed_urls) ? payload.failed_urls : [],
  }
}

export function hasCrawlTarget(account) {
  return Boolean(account?.website || account?.normalized_domain)
}

export function accountWebsiteLabel(account) {
  return account?.website || account?.normalized_domain || 'No website available'
}

export function accountCrawlSummary(account, crawlState) {
  if (!crawlState) return hasCrawlTarget(account) ? 'Ready to crawl this company website.' : 'No website is available yet for crawling.'
  if (crawlState.crawl_status === 'running') return 'Crawler is running now. Status will refresh automatically.'
  if (crawlState.crawl_status === 'completed') {
    return `${crawlState.pages_saved} page${crawlState.pages_saved === 1 ? '' : 's'} saved • ${crawlState.facts_saved} fact${crawlState.facts_saved === 1 ? '' : 's'} extracted`
  }
  if (crawlState.crawl_status === 'failed') {
    return crawlState.failed_urls.length
      ? `${crawlState.failed_urls.length} URL${crawlState.failed_urls.length === 1 ? '' : 's'} failed during the last crawl`
      : 'The last crawl failed before usable results were saved.'
  }
  return hasCrawlTarget(account) ? 'Ready to crawl this company website.' : 'No website is available yet for crawling.'
}

export function crawlStatusLabel(crawlState) {
  const status = crawlState?.crawl_status
  if (status === 'running') return 'Crawl in progress'
  if (status === 'completed') return 'Crawl completed'
  if (status === 'failed') return 'Crawl failed'
  return 'Not crawled yet'
}

export function crawlStatusClass(crawlState) {
  return `status-${crawlState?.crawl_status || 'idle'}`
}

export function formatDateTime(value, fallback = 'Not available') {
  if (!value) return fallback
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return fallback
  return parsed.toLocaleString()
}
