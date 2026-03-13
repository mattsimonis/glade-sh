const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:3000',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'Mobile Safari',
      use: { ...devices['iPhone 13'] },
    },
    {
      name: 'iPhone landscape',
      use: { ...devices['iPhone 13 landscape'] },
    },
    {
      name: 'iPad portrait',
      use: { ...devices['iPad (gen 7)'] },
    },
    {
      name: 'iPad landscape',
      use: { ...devices['iPad (gen 7) landscape'] },
    },
  ],
});
