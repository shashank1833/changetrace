// Kept in the monorepo-level E2E suite; dependency is owned by the web package.
import { expect, test } from '../../apps/web/node_modules/@playwright/test/index'

test('business change simulation from repository through decision and export', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('Know what your change will')).toBeVisible()
  await page.getByLabel('Change request').fill(
    'Add RETURNED as an order status after shipment and refund after successful warehouse inspection.',
  )
  await page.getByRole('button', { name: /optional proposed git diff/i }).click()
  await page.getByLabel('Proposed Git diff').fill(`diff --git a/backend/models/order.py b/backend/models/order.py
--- a/backend/models/order.py
+++ b/backend/models/order.py
@@ -7,2 +7,3 @@ class OrderStatus(str, Enum):
     SHIPPED = "SHIPPED"
+    RETURNED = "RETURNED"
     CANCELLED = "CANCELLED"
`)
  await page.getByRole('button', { name: /simulate change/i }).click()
  await expect(page.getByText('CHANGE SIMULATION')).toBeVisible({ timeout: 30_000 })
  await page.getByRole('button', { name: 'Impact', exact: true }).click()
  await expect(page.getByText('Why these components are affected')).toBeVisible()
  await page.getByRole('button', { name: 'Risks', exact: true }).click()
  await expect(page.getByText('What could break')).toBeVisible()
  await page.getByRole('button', { name: 'Evidence', exact: true }).click()
  await expect(page.getByText('Inspect every conclusion')).toBeVisible()
  await page.getByRole('button', { name: 'Test Gaps' }).click()
  await expect(page.getByText('Verification coverage')).toBeVisible()
  await expect(page.getByText(/confirmed missing scenarios; uncertain coverage is shown separately/)).toBeVisible()
  await page.getByRole('button', { name: 'Decision' }).click()
  await expect(page.getByText(/REVIEW BEFORE IMPLEMENTATION|BLOCK CHANGE|GO TO IMPLEMENTATION/).first()).toBeVisible()
  const markdownDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: /Export Markdown/i }).click()
  await expect((await markdownDownload).suggestedFilename()).toMatch(/\.md$/)
  const jsonDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: /Export JSON/i }).click()
  await expect((await jsonDownload).suggestedFilename()).toMatch(/\.json$/)
})
