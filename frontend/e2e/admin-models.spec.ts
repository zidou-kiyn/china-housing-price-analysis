import { expect, test } from '@playwright/test'
import { loginAsAdmin } from './helpers'

test.describe('模型管理页', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page)
    await page.goto('/admin/models')
    await expect(page.locator('.el-table__body tbody tr').first()).toBeVisible({
      timeout: 10_000,
    })
  })

  test('版本列表加载且活跃行按钮禁用', async ({ page }) => {
    const rows = page.locator('.el-table__body tbody tr')
    expect(await rows.count()).toBeGreaterThanOrEqual(1)

    const activeRow = rows.filter({ has: page.locator('.el-tag', { hasText: '活跃' }) })
    await expect(activeRow).toHaveCount(1)
    await expect(activeRow.locator('button', { hasText: '设为活跃' })).toBeDisabled()
  })

  test('提交训练出现进行中状态并完成刷新', async ({ page }) => {
    const before = await page.locator('.el-table__body tbody tr').count()

    await page.locator('.train-form button', { hasText: '开始训练' }).click()
    await expect(page.locator('.train-progress .el-tag')).toContainText(/等待中|训练中/, {
      timeout: 5_000,
    })
    await expect(page.locator('.train-form button', { hasText: '开始训练' })).toBeDisabled()

    // 最小数据真跑（秒级），等待完成后版本表自动多一行
    await expect(page.locator('.train-progress .el-tag')).toContainText('成功', {
      timeout: 60_000,
    })
    await expect(page.locator('.el-table__body tbody tr')).toHaveCount(before + 1)
  })

  test('切换活跃模型（切到非活跃版本再切回）', async ({ page }) => {
    const rows = page.locator('.el-table__body tbody tr')
    const activeText = await rows
      .filter({ has: page.locator('.el-tag', { hasText: '活跃' }) })
      .first()
      .innerText()

    const inactiveRow = rows
      .filter({ hasNot: page.locator('.el-tag', { hasText: '活跃' }) })
      .first()
    const targetText = await inactiveRow.innerText()
    await inactiveRow.locator('button', { hasText: '设为活跃' }).click()
    await page.locator('.el-message-box button', { hasText: '切换' }).click()

    const [name, version] = targetText.split(/\s+/)
    const newActive = rows.filter({ has: page.locator('.el-tag', { hasText: '活跃' }) })
    await expect(newActive).toContainText(version, { timeout: 5_000 })

    // 恢复原活跃版本
    const [origName, origVersion] = activeText.split(/\s+/)
    const origRow = rows.filter({ hasText: origName }).filter({ hasText: origVersion })
    await origRow.locator('button', { hasText: '设为活跃' }).click()
    await page.locator('.el-message-box button', { hasText: '切换' }).click()
    await expect(
      rows.filter({ has: page.locator('.el-tag', { hasText: '活跃' }) }),
    ).toContainText(origVersion, { timeout: 5_000 })
  })
})
