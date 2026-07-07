import { defineConfig, devices } from '@playwright/test'

/**
 * E2E 依赖本地 dev 环境：
 * - backend: uvicorn app.main:app --port 8000（数据库需已有泉州数据 + admin 账号）
 * - frontend: 自动复用已启动的 vite (5173)，未启动时自动拉起
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: false,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 30_000,
  },
})
