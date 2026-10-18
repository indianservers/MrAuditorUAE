import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  testMatch: "phase10.spec.ts",
  workers: 1,
  timeout: 240000,
  expect: { timeout: 25000 },
  reporter: [
    ["list"],
    ["json", { outputFile: "../docs/phase-10/browser-results.json" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:3003",
    viewport: { width: 1600, height: 1000 },
    reducedMotion: "reduce",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
