import React, { useContext, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listSellers, listIcps, listAccounts } from '../api.js'
import { AuthContext } from '../App.jsx'

const ONBOARDING_DISMISSED_KEY = 'icp-onboarding-dismissed'

export default function HomePage() {
  const { token } = useContext(AuthContext)
  const navigate = useNavigate()

  const [sellers, setSellers] = useState([])
  const [icps, setIcps] = useState([])
  const [accounts, setAccounts] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [onboardingDismissed, setOnboardingDismissed] = useState(
    () => localStorage.getItem(ONBOARDING_DISMISSED_KEY) === 'true'
  )

  useEffect(() => { document.title = 'Dashboard — ICP Search' }, [])

  useEffect(() => {
    if (!token) return
    setLoading(true)
    listSellers(token)
      .then(async (data) => {
        setSellers(data)
        if (data.length > 0) {
          const sellerId = data[0].id
          const [icpData, accountData] = await Promise.all([
            listIcps(token, sellerId),
            listAccounts(token, sellerId),
          ])
          setIcps(icpData)
          setAccounts(accountData)
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [token])

  const firstSeller = sellers[0] || null
  const step1Done = sellers.length > 0
  const step2Done = step1Done && icps.length > 0
  const step3Done = step2Done && accounts.length > 0

  const showSetupGuide = !onboardingDismissed && !step3Done

  function dismissOnboarding() {
    localStorage.setItem(ONBOARDING_DISMISSED_KEY, 'true')
    setOnboardingDismissed(true)
  }

  const setupSteps = [
    {
      num: 1,
      title: 'Create a workspace',
      desc: 'Your home base for ICPs and account data.',
      cta: 'Create workspace',
      done: step1Done,
      active: !step1Done,
      onClick: () => navigate('/sellers'),
    },
    {
      num: 2,
      title: 'Define your ICP',
      desc: 'Describe the type of company you want to reach.',
      cta: 'Add ICP',
      done: step2Done,
      active: step1Done && !step2Done,
      onClick: () => firstSeller && navigate(`/sellers/${firstSeller.id}/icps`),
      disabled: !step1Done,
    },
    {
      num: 3,
      title: 'Discover accounts',
      desc: 'Search for companies that match your profile.',
      cta: 'Start search',
      done: step3Done,
      active: step2Done && !step3Done,
      onClick: () => firstSeller && navigate(`/sellers/${firstSeller.id}/accounts`),
      disabled: !step2Done,
    },
  ]

  return (
    <>
      {error && <p className="notice error" role="alert">{error}</p>}
      {loading && <p className="empty">Loading...</p>}

      {showSetupGuide && (
        <section className="panel setup-guide">
          <div className="setup-guide-header">
            <div>
              <h2>Get started</h2>
              <p className="setup-guide-sub">Three steps to your first target account list.</p>
            </div>
            <button className="ghost" type="button" onClick={dismissOnboarding}>
              Dismiss
            </button>
          </div>
          <ol className="setup-steps">
            {setupSteps.map((step) => (
              <li
                key={step.num}
                className={`setup-step${step.done ? ' done' : step.active ? ' active' : ' pending'}`}
              >
                <span className="step-num" aria-hidden="true">
                  {step.done ? '✓' : step.num}
                </span>
                <div className="step-body">
                  <strong>{step.title}</strong>
                  <span>{step.desc}</span>
                </div>
                {!step.done && (
                  <button
                    type="button"
                    className={step.active ? '' : 'ghost'}
                    disabled={step.disabled}
                    onClick={step.onClick}
                  >
                    {step.cta}
                  </button>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="content-grid">
        <article className="panel">
          <p className="eyebrow">Workspaces</p>
          <h2>Seller workspaces</h2>
          <p className="empty">
            {firstSeller
              ? `Working from ${firstSeller.name}${sellers.length > 1 ? ` — ${sellers.length} workspaces total` : ''}.`
              : 'No workspaces yet — create one to get started.'}
          </p>
          <button type="button" onClick={() => navigate('/sellers')}>
            Manage workspaces
          </button>
        </article>

        <article className="panel">
          <p className="eyebrow">Ideal Customer Profiles</p>
          <h2>Your ICPs</h2>
          <p className="empty">
            {icps.length > 0
              ? `${icps.length} ICP${icps.length === 1 ? '' : 's'} defined for ${firstSeller?.name || 'this workspace'}.`
              : firstSeller
                ? 'No ICPs yet — create one to start discovering accounts.'
                : 'Create a workspace first, then define your ICPs.'}
          </p>
          <button
            className="ghost"
            type="button"
            disabled={!firstSeller}
            onClick={() => firstSeller && navigate(`/sellers/${firstSeller.id}/icps`)}
          >
            Manage ICPs
          </button>
        </article>

        <article className="panel">
          <p className="eyebrow">Account Discovery</p>
          <h2>Target accounts</h2>
          <p className="empty">
            {accounts.length
              ? `${accounts.length} saved account${accounts.length === 1 ? '' : 's'} — open discovery to review.`
              : icps.length === 0
                ? 'Define an ICP first, then run targeted company searches.'
                : 'No accounts saved yet — run a discovery search to find targets.'}
          </p>
          <button
            className="ghost"
            type="button"
            disabled={!firstSeller || icps.length === 0}
            onClick={() => firstSeller && navigate(`/sellers/${firstSeller.id}/accounts`)}
          >
            Discover accounts
          </button>
        </article>
      </section>
    </>
  )
}
