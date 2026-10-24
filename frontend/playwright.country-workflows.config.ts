import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  testMatch: "country-workflows.spec.ts",
  workers: 1,
  timeout: 120000,
  expect: { timeout: 30000 },
  reporter: [
    ["list"],
    ["json", { outputFile: "../docs/country-workflows/browser-results.json" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:3010",
    viewport: { width: 1600, height: 1100 },
    screenshot: "only-on-failure",
  },
});
