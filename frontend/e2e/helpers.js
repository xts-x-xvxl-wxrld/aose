/**
 * Shared mock helpers for ICP Search E2E tests.
 * All API calls are intercepted — no live backend required.
 */

export const FAKE_TOKEN = 'test-token-abc123'

export const FAKE_SELLER = { id: 1, name: 'Acme Corp', created_at: '2024-01-01T00:00:00Z' }

export const FAKE_ICP = {
  id: 1,
  seller_id: 1,
  name: 'Mid-market SaaS',
  description: 'B2B SaaS companies 50-500 employees',
  created_at: '2024-01-01T00:00:00Z',
}

export const FAKE_ACCOUNT = {
  id: 1,
  seller_id: 1,
  name: 'Globex Corp',
  domain: 'globex.com',
  created_at: '2024-01-01T00:00:00Z',
}

/**
 * Set up standard API mocks.
 * Call this at the start of any test that needs an authenticated state.
 */
export async function mockAuthenticatedAPIs(page) {
  // Auth
  await page.route('**/auth/login', (route) =>
    route.fulfill({ json: { access_token: FAKE_TOKEN, token_type: 'bearer' } })
  )
  await page.route('**/auth/register', (route) =>
    route.fulfill({ status: 201, json: { id: 1, email: 'test@example.com' } })
  )

  // Sellers
  await page.route('**/sellers/', (route) => {
    if (route.request().method() === 'GET')
      return route.fulfill({ json: [FAKE_SELLER] })
    if (route.request().method() === 'POST')
      return route.fulfill({ status: 201, json: FAKE_SELLER })
  })
  await page.route(`**/sellers/${FAKE_SELLER.id}`, (route) =>
    route.fulfill({ json: FAKE_SELLER })
  )
  await page.route(`**/sellers/${FAKE_SELLER.id}/summary`, (route) =>
    route.fulfill({
      json: {
        icps: { count: 1, last_added: '2024-01-01T00:00:00Z' },
        accounts: { count: 1, last_added: '2024-01-01T00:00:00Z' },
        contacts: { count: 0, last_added: null },
        pending_instruction_alerts: 0,
      },
    })
  )

  // ICPs
  await page.route(`**/sellers/${FAKE_SELLER.id}/icps/`, (route) => {
    if (route.request().method() === 'GET')
      return route.fulfill({ json: [FAKE_ICP] })
    if (route.request().method() === 'POST')
      return route.fulfill({ status: 201, json: FAKE_ICP })
  })

  // Accounts
  await page.route(`**/sellers/${FAKE_SELLER.id}/accounts/`, (route) => {
    if (route.request().method() === 'GET')
      return route.fulfill({ json: [FAKE_ACCOUNT] })
    if (route.request().method() === 'POST')
      return route.fulfill({ status: 201, json: FAKE_ACCOUNT })
  })

  // Contacts
  await page.route(`**/sellers/${FAKE_SELLER.id}/contacts/**`, (route) =>
    route.fulfill({ json: [] })
  )
}

/**
 * Log in via the UI and wait for the workspace to load.
 */
export async function loginViaUI(page) {
  await page.goto('/login')
  await page.getByLabel('Email').fill('test@example.com')
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  // Wait for workspace to appear (left sidebar)
  await page.waitForSelector('[aria-label="Left sidebar"]')
}
