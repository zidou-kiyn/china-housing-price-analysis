import { expect, test } from '@playwright/test'

test('UI 登录成功后导航栏显示用户名', async ({ page }) => {
  await page.goto('/login')
  await page.getByPlaceholder('用户名').fill('admin')
  await page.getByPlaceholder('密码').fill('admin123456')
  await page.locator('button', { hasText: '登录' }).click()
  await expect(page.locator('.username')).toContainText('admin', { timeout: 10_000 })
})
