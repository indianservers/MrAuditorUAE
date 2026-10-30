import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  testMatch: [
    "release-smoke.spec.ts",
    "country-report-release.spec.ts",
    "form26-fields-release.spec.ts",
    "annual-gst-release.spec.ts",
    "foreign-obligation-release.spec.ts",
    "inventory-fifo-release.spec.ts",
  ],
  workers: 1,
  reporter: "list",
  use: {
    baseURL: process.env.AUDITOS_E2E_ORIGIN || "http://127.0.0.1:3005",
    screenshot: "only-on-failure",
  },
});
