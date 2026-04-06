import { test, expect } from '@playwright/test'
import { mockAuthenticatedAPIs, loginViaUI, FAKE_SELLER, FAKE_ICP, FAKE_ACCOUNT } from './helpers.js'

test.describe('Workspace navigation', () => {
  test.beforeEach(async ({ page }) => {
    await mockAuthenticatedAPIs(page)
    await loginViaUI(page)
    // Expand the seller tree
    await page.getByRole('button', { name: 'Expand' }).first().click()
  })

  test('clicking Accounts shows account list', async ({ page }) => {
    await page.getByRole('button', { name: 'Accounts' }).click()
    await expect(page.getByText(FAKE_ACCOUNT.name)).toBeVisible()
  })

  test('clicking ICPs shows ICP list', async ({ page }) => {
    await page.getByRole('button', { name: 'ICPs' }).click()
    await expect(page.getByText(FAKE_ICP.name)).toBeVisible()
  })

  test('clicking seller name opens seller overview', async ({ page }) => {
    await page.getByText(FAKE_SELLER.name).click()
    // Seller overview should render the seller name in the main area
    await expect(page.locator('main')).toContainText(FAKE_SELLER.name)
  })
})

test.describe('Error states', () => {
  test('API failure on sellers shows error in sidebar', async ({ page }) => {
    await page.route('**/sellers/', (route) =>
      route.fulfill({ status: 500, json: { detail: 'Internal server error' } })
    )
    // Auth still needs to work
    await page.route('**/auth/login', (route) =>
      route.fulfill({ json: { access_token: 'tok', token_type: 'bearer' } })
    )

    await loginViaUI(page)
    await expect(page.locator('[aria-label="Left sidebar"]')).toContainText(/server error|500/i)
  })
})
