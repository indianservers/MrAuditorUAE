import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  testMatch: /qa-crud\.spec\.ts/,
  workers: 1,
  timeout: 180000,
  expect: { timeout: 20000 },
  reporter: [
    ["list"],
    ["json", { outputFile: "../docs/qa-crud/browser-results.json" }],
  ],
  use: {
    actionTimeout: 20000,
    navigationTimeout: 45000,
    baseURL: "http://127.0.0.1:3006",
    viewport: { width: 1600, height: 1000 },
    reducedMotion: "reduce",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
