import { defineConfig } from "@playwright/test";
import base from "./playwright.country-workflows.config";
export default defineConfig({
  ...base,
  testMatch: "completion-freshness.spec.ts",
  reporter: [
    ["list"],
    [
      "json",
      {
        outputFile:
          "../docs/phase-12/completion-freshness-browser-results.json",
      },
    ],
  ],
});
