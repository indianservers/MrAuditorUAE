import { defineConfig } from "@playwright/test";
import base from "./playwright.country-workflows.config";
export default defineConfig({
  ...base,
  testMatch: "bank-matching-candidates.spec.ts",
  reporter: [
    ["list"],
    [
      "json",
      {
        outputFile: "../docs/phase-12/matching-candidates-browser-results.json",
      },
    ],
  ],
});
