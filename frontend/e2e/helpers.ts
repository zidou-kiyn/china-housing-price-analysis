import type { Page } from '@playwright/test'

// backend 端口不再暴露到宿主机，E2E 的 API 请求默认经前端 dev server 代理转发
export const API_BASE = process.env.E2E_API_BASE ?? 'http://localhost:5173/api/v1'

/** 通过 API 登录 admin 并把 token 注入 localStorage（绕开 UI 登录，加速用例）。 */
export async function loginAsAdmin(page: Page) {
  const resp = await page.request.post(`${API_BASE}/auth/login`, {
    data: { username: 'admin', password: 'admin123456' },
  })
  if (!resp.ok()) {
    throw new Error(`admin 登录失败（${resp.status()}）：请确认 dev 数据库已有种子账号`)
  }
  const { access_token } = await resp.json()
  await page.addInitScript((token: string) => localStorage.setItem('token', token), access_token)
}
