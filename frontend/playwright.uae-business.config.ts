import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  testMatch: "uae-business-cases.spec.ts",
  workers: 1,
  timeout: 180000,
  expect: { timeout: 25000 },
  reporter: [
    ["list"],
    [
      "json",
      {
        outputFile: "../docs/mr-auditor-business/evidence/browser-results.json",
      },
    ],
  ],
  use: {
    actionTimeout:15000,
    baseURL: "http://127.0.0.1:3047",
    viewport: { width: 1500, height: 1100 },
    screenshot: "only-on-failure",
  },
});
