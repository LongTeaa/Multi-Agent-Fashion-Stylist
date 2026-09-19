import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:3000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command: 'python ../backend/scripts/run_browser_e2e.py',
      url: 'http://127.0.0.1:8011/health',
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: 'npm run dev -- --hostname 127.0.0.1',
      url: 'http://127.0.0.1:3000',
      env: { NEXT_PUBLIC_API_URL: 'http://127.0.0.1:8011' },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
