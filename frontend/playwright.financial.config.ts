import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  testMatch: "financial-reporting.spec.ts",
  workers: 1,
  timeout: 180000,
  expect: { timeout: 30000 },
  reporter: [
    ["list"],
    [
      "json",
      { outputFile: "../docs/financial-reporting/browser-results.json" },
    ],
  ],
  use: {
    baseURL: "http://127.0.0.1:3008",
    viewport: { width: 1600, height: 1100 },
    screenshot: "only-on-failure",
  },
});
