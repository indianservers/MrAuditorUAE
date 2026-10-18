import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  testMatch: "phase4.spec.ts",
  workers: 1,
  fullyParallel: false,
  timeout: 180000,
  expect: { timeout: 15000 },
  reporter: [
    ["list"],
    ["json", { outputFile: "../docs/phase-4/playwright-results.json" }],
  ],
  use: {
    actionTimeout: 15000,
    navigationTimeout: 30000,
    baseURL: process.env.FRONTEND_URL || "http://127.0.0.1:3000",
    viewport: { width: 1672, height: 1050 },
    reducedMotion: "reduce",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
