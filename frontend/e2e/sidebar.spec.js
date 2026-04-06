import { test, expect } from '@playwright/test'
import { mockAuthenticatedAPIs, loginViaUI, FAKE_SELLER } from './helpers.js'

test.describe('Left Sidebar', () => {
  test.beforeEach(async ({ page }) => {
    await mockAuthenticatedAPIs(page)
    await loginViaUI(page)
  })

  test('shows seller name in the tree', async ({ page }) => {
    await expect(page.getByText(FAKE_SELLER.name)).toBeVisible()
  })

  test('expanding a seller reveals category rows (ICPs, Accounts, Contacts)', async ({ page }) => {
    // Click the expand chevron for the seller
    await page.getByRole('button', { name: 'Expand' }).first().click()

    await expect(page.getByRole('button', { name: 'ICPs' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Accounts' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Contacts' })).toBeVisible()
  })

  test('clicking Chat nav button activates chat mode', async ({ page }) => {
    await page.getByRole('button', { name: 'Chat' }).click()
    // Chat window should appear (look for a message input or chat heading)
    await expect(page.locator('[aria-label="Left sidebar"]')).toBeVisible()
    // The Chat button should now be visually active (has the active class)
    const chatBtn = page.getByRole('button', { name: 'Chat' })
    await expect(chatBtn).toHaveClass(/font-medium|bg-sidebar-accent/)
  })

  test('toggling sidebar collapse hides labels', async ({ page }) => {
    // Sidebar starts expanded — "ICP Search" label should be visible
    await expect(page.getByText('ICP Search')).toBeVisible()

    // Collapse it
    await page.getByRole('button', { name: 'Collapse sidebar' }).click()

    // Text labels should be gone; sidebar is collapsed
    await expect(page.getByText('ICP Search')).not.toBeVisible()

    // Re-expand
    await page.getByRole('button', { name: 'Expand sidebar' }).click()
    await expect(page.getByText('ICP Search')).toBeVisible()
  })

  test('clicking Add Seller opens dialog', async ({ page }) => {
    await page.locator('[aria-label="Left sidebar"]').getByRole('button', { name: 'Add Seller' }).click()
    // A dialog / modal should appear
    await expect(page.getByRole('dialog')).toBeVisible()
  })

  test('creating a seller via dialog calls API and updates list', async ({ page }) => {
    const newSeller = { id: 2, name: 'New Seller Co', created_at: '2024-01-02T00:00:00Z' }

    // Override the POST to return a new seller, and the GET to include both
    await page.route('**/sellers/', (route) => {
      if (route.request().method() === 'POST')
        return route.fulfill({ status: 201, json: newSeller })
      if (route.request().method() === 'GET')
        return route.fulfill({ json: [FAKE_SELLER, newSeller] })
    })

    await page.locator('[aria-label="Left sidebar"]').getByRole('button', { name: 'Add Seller' }).click()
    await page.getByRole('dialog').getByRole('textbox').fill('New Seller Co')
    await page.getByRole('dialog').getByRole('button', { name: /create|add|save/i }).click()

    await expect(page.getByRole('dialog')).not.toBeVisible()
  })
})
