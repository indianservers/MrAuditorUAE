import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  testMatch: "global-platform.spec.ts",
  workers: 1,
  timeout: 180000,
  expect: { timeout: 30000 },
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:3006",
    viewport: { width: 1600, height: 1000 },
    screenshot: "only-on-failure",
  },
});
