import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  testMatch: "client-collaboration.spec.ts",
  workers: 1,
  timeout: 120000,
  expect: { timeout: 30000 },
  reporter: [
    ["list"],
    [
      "json",
      {
        outputFile:
          "../docs/phase3/evidence/collaboration-browser-results.json",
      },
    ],
  ],
  use: {
    baseURL: "http://127.0.0.1:3006",
    viewport: { width: 1400, height: 1000 },
    trace: "off",
    screenshot: "off",
  },
});
