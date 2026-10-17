import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: [
    ["list"],
    ["json", { outputFile: "../docs/phase-3/playwright-results.json" }],
  ],
  use: {
    baseURL: process.env.FRONTEND_URL || "http://127.0.0.1:3000",
    viewport: { width: 1672, height: 941 },
    reducedMotion: "reduce",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
