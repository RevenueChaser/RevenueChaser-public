// The browser tier of the `web` CI job: the frame at 1187 and 1884 px, light and dark (ADR decision 7).
import { defineConfig, devices } from '@playwright/test';

const PORT = 4173;
const URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: './tests',
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: 'line',
  use: { baseURL: URL },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  // `vite preview` serves the production build, so the browser tier tests what the door will serve.
  webServer: { command: 'npm run preview', url: URL, reuseExistingServer: false, timeout: 120_000 },
});
