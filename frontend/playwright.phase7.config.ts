import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  testMatch: "phase7.spec.ts",
  workers: 1,
  timeout: 240000,
  expect: { timeout: 20000 },
  reporter: [
    ["list"],
    ["json", { outputFile: "../docs/phase-7/playwright-results.json" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:3001",
    viewport: { width: 1672, height: 1050 },
    reducedMotion: "reduce",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
