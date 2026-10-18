import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  testMatch: "phase9.spec.ts",
  workers: 1,
  timeout: 180000,
  expect: { timeout: 25000 },
  reporter: [
    ["list"],
    ["json", { outputFile: "../docs/phase-9/browser-results.json" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:3002",
    viewport: { width: 1600, height: 1000 },
    reducedMotion: "reduce",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
