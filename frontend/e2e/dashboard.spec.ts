import { expect, test } from '@playwright/test'
import { loginAsAdmin } from './helpers'

test.describe('大屏多图联动', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
    await page.goto('/dashboard')
    await expect(page.locator('.dashboard-page .el-tag')).toContainText('泉州', {
      timeout: 15_000,
    })
  })

  test('四面板画布齐全', async ({ page }) => {
    await expect(page.locator('.dashboard-page canvas')).toHaveCount(4, { timeout: 15_000 })
  })

  test('柱状图点选联动与返回全市', async ({ page }) => {
    const tag = page.locator('.dashboard-page .el-tag')
    const bar = page.locator('.dashboard-page canvas').nth(1)
    await expect(bar).toBeVisible()
    // 等首屏数据渲染完成再取坐标
    await page.waitForTimeout(1500)
    const box = await bar.boundingBox()
    if (!box) throw new Error('柱状图画布不可见')
    // 第一个类目柱中心（grid left 60 + 半带宽），y 取贴近 x 轴处保证命中非零柱
    await page.mouse.click(box.x + 75, box.y + box.height - 80)
    await expect(tag).not.toContainText('泉州', { timeout: 5_000 })

    await page.getByRole('button', { name: '返回全市' }).click()
    await expect(tag).toContainText('泉州', { timeout: 5_000 })
  })
})
