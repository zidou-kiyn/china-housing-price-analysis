import { expect, test } from '@playwright/test'

test('访客访问大屏跳转登录页', async ({ page }) => {
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/\/login\?redirect=/)
})

test('首页选择城市后出图', async ({ page }) => {
  await page.goto('/')
  const emptyHint = page.getByText('请选择一个城市开始分析')
  if (await emptyHint.isVisible().catch(() => false)) {
    // el-select 的 input 会被 placeholder 拦截指针事件，点外层容器
    await page.locator('.el-select').first().click()
    await page.locator('.el-select-dropdown__item', { hasText: '泉州' }).first().click()
  }
  await expect(page.locator('canvas').first()).toBeVisible({ timeout: 10_000 })
})

test('排行榜公开可见且有数据行', async ({ page }) => {
  await page.goto('/rank')
  const rows = page.locator('.el-table__body tr')
  await expect(rows.first()).toBeVisible({ timeout: 10_000 })
  expect(await rows.count()).toBeGreaterThan(0)
})
