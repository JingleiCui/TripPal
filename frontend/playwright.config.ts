import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "e2e",
  timeout: 90000,
  workers: 1,
  use: {
    baseURL: process.env.TRIPAL_E2E_BASE_URL || "http://127.0.0.1:8808",
    channel: "chrome",
    headless: true,
    trace: "retain-on-failure",
  },
  reporter: [["list"], ["json", { outputFile: "../reports/browser-results.json" }]],
});
