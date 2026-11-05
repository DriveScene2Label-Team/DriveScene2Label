import { defineConfig, devices } from '@playwright/test';

// E2E runs the built app with `vite preview`. Every `/api/*` call is answered by route fixtures that follow the
// real Spring DTOs (tests/e2e/fixtures). These tests prove UI flows, not live-server integration.
export default defineConfig({
  testDir: './tests/e2e',
  outputDir: './test-results',
  fullyParallel: true,
  // Six viewport projects run in parallel against one preview server; 5 s was too tight for first-frame loads under that load.
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  use: { baseURL: 'http://127.0.0.1:4173', trace: 'retain-on-failure', locale: 'ko-KR' },
  webServer: {
    command: 'npm run build && npx vite preview --host 127.0.0.1 --port 4173 --strictPort',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: { API_PROXY_TARGET: 'http://127.0.0.1:9' },
  },
  projects: [
    { name: 'desktop-1440', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
    { name: 'desktop-1280', use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } }, grep: /@layout/ },
    { name: 'tablet-1024', use: { ...devices['Desktop Chrome'], viewport: { width: 1024, height: 768 } }, grep: /@layout/ },
    { name: 'tablet-768', use: { ...devices['Desktop Chrome'], viewport: { width: 768, height: 1024 } }, grep: /@layout/ },
    { name: 'mobile-375', use: { ...devices['Desktop Chrome'], viewport: { width: 375, height: 812 }, hasTouch: true }, grep: /@layout/ },
    // Playwright's headless WebKit engine (not the Safari app): keyboard/focus/reduced-motion checks only.
    { name: 'webkit-1440', use: { ...devices['Desktop Safari'], viewport: { width: 1440, height: 900 } }, grep: /@a11y/ },
  ],
});
