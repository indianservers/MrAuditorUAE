import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  testMatch: "mr-auditor-phase1.spec.ts",
  workers: 1,
  timeout: 240000,
  expect: { timeout: 25000 },
  reporter: [
    ["list"],
    [
      "json",
      { outputFile: "../docs/qa/mr-auditor-phase1/browser-results.json" },
    ],
  ],
  use: {
    actionTimeout: 20000,
    navigationTimeout: 45000,
    baseURL: "http://127.0.0.1:3006",
    viewport: { width: 1600, height: 1100 },
    screenshot: "only-on-failure",
  },
});
