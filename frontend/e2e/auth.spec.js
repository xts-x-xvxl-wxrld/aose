import { test, expect } from '@playwright/test'
import { mockAuthenticatedAPIs, loginViaUI, FAKE_TOKEN } from './helpers.js'

test.describe('Authentication', () => {
  test('unauthenticated users are redirected to /login', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/login/)
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  })

  test('login form requires both fields before enabling submit', async ({ page }) => {
    await page.goto('/login')
    const submit = page.getByRole('button', { name: 'Sign in' })
    await expect(submit).toBeDisabled()

    await page.getByLabel('Email').fill('test@example.com')
    await expect(submit).toBeDisabled() // still needs password

    await page.getByLabel('Password').fill('pass')
    await expect(submit).toBeEnabled()
  })

  test('successful login lands on workspace', async ({ page }) => {
    await mockAuthenticatedAPIs(page)
    await loginViaUI(page)

    // Left sidebar is the workspace root
    await expect(page.locator('[aria-label="Left sidebar"]')).toBeVisible()
    await expect(page).not.toHaveURL(/\/login/)
  })

  test('failed login shows error message', async ({ page }) => {
    await page.route('**/auth/login', (route) =>
      route.fulfill({ status: 401, json: { detail: 'Invalid credentials' } })
    )

    await page.goto('/login')
    await page.getByLabel('Email').fill('bad@example.com')
    await page.getByLabel('Password').fill('wrongpass')
    await page.getByRole('button', { name: 'Sign in' }).click()

    await expect(page.getByRole('alert')).toContainText(/401|Invalid credentials/i)
    await expect(page).toHaveURL(/\/login/)
  })

  test('switching to register mode changes heading and button', async ({ page }) => {
    await page.goto('/login')
    await page.getByRole('button', { name: 'Need an account?' }).click()

    await expect(page.getByRole('heading', { name: 'Create account' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Register', exact: true })).toBeVisible()
  })

  test('successful registration shows confirmation and returns to login mode', async ({ page }) => {
    await page.route('**/auth/register', (route) =>
      route.fulfill({ status: 201, json: { id: 1, email: 'new@example.com' } })
    )

    await page.goto('/login')
    await page.getByRole('button', { name: 'Need an account?' }).click()
    await page.getByLabel('Email').fill('new@example.com')
    await page.getByLabel('Password').fill('newpass123')
    await page.getByRole('button', { name: 'Register', exact: true }).click()

    // Should show success notice and flip back to login mode
    await expect(page.getByRole('status')).toContainText(/Account created/i)
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  })

  test('already-logged-in user is not shown the login form', async ({ page }) => {
    await mockAuthenticatedAPIs(page)

    // Inject token before React renders so the authStore reads it on init.
    await page.addInitScript((token) => {
      localStorage.setItem('icp-search-token', token)
    }, FAKE_TOKEN)

    await page.goto('/login')

    // LoginPage returns null when a token is present (no form rendered).
    // Note: navigate('/') during render is a known React anti-pattern and
    // does not always fire — but the form guard itself works correctly.
    await expect(page.locator('form')).not.toBeAttached()
  })
})
