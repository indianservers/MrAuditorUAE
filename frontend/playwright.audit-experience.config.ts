import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  testMatch: "audit-experience.spec.ts",
  workers: 1,
  timeout: 120000,
  expect: { timeout: 30000 },
  reporter: [
    ["list"],
    ["json", { outputFile: "../docs/ui-refresh/browser-results.json" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:3006",
    viewport: { width: 1600, height: 1100 },
    trace: "off",
  },
});
