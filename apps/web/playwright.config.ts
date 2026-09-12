import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: '../../tests/e2e',
  timeout: 45_000,
  use: { baseURL: 'http://127.0.0.1:5187', trace: 'on-first-retry' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'cd ../.. && python -m uvicorn changetrace_api.main:app --app-dir apps/api --host 127.0.0.1 --port 8017',
      url: 'http://127.0.0.1:8017/health',
      reuseExistingServer: false,
      env: { CHANGETRACE_LOCAL_REPOSITORY_ROOT: '.' },
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5187',
      url: 'http://127.0.0.1:5187',
      reuseExistingServer: false,
      env: { VITE_API_PROXY: 'http://127.0.0.1:8017', VITE_PORT: '5187' },
    },
  ],
})
