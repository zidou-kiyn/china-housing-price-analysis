import { expect, test } from '@playwright/test'
import { loginAsAdmin } from './helpers'

test.describe('数据管理页', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
    await page.goto('/admin/data')
  })

  test('城市覆盖表加载且泉州显示有数据有图', async ({ page }) => {
    await expect(page.locator('.el-table__body tbody tr').first()).toBeVisible({
      timeout: 10_000,
    })

    await page.locator('.filter-keyword input').fill('泉州')
    await page.locator('.filter-bar button', { hasText: '搜索' }).click()
    const row = page.locator('.el-table__body tbody tr').first()
    await expect(row).toContainText('泉州', { timeout: 5_000 })
    await expect(row).toContainText('qz')
    // 已采集城市：有最新月份 tag 与地图「有」
    await expect(row.locator('.el-tag')).toHaveCount(2)
    await expect(row).not.toContainText('无数据')
  })

  test('未选择城市时批量按钮禁用，勾选后可用', async ({ page }) => {
    await expect(page.locator('.el-table__body tbody tr').first()).toBeVisible({
      timeout: 10_000,
    })
    const collectBtn = page.locator('.batch-actions button', { hasText: '采集所选' })
    await expect(collectBtn).toBeDisabled()

    await page.locator('.el-table__body tbody tr .el-checkbox').first().click()
    await expect(collectBtn).toBeEnabled()
    await expect(collectBtn).toContainText('采集所选（1）')
  })
})

test('城市地图经 geo API 加载', async ({ page }) => {
  await loginAsAdmin(page)
  const geoResp = page.waitForResponse(
    (resp) => resp.url().includes('/api/v1/geo/') && resp.status() === 200,
    { timeout: 15_000 },
  )
  await page.goto('/map')
  const resp = await geoResp
  const body = await resp.json()
  expect(body.type).toBe('FeatureCollection')
})
