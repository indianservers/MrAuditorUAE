import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e", testMatch: /qa-campaign\.spec\.ts/,
  workers: 1, timeout: 900000, expect: { timeout: 20000 },
  reporter: [["list"], ["json", { outputFile: "../docs/qa-campaign/browser-results.json" }]],
  use: { baseURL: "http://127.0.0.1:3006", viewport: { width: 1600, height: 900 }, reducedMotion: "reduce", trace: "retain-on-failure", screenshot: "only-on-failure" },
});
