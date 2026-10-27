import { defineConfig } from "@playwright/test";
import base from "./playwright.country-workflows.config";
export default defineConfig({
  ...base,
  testMatch: "generic-matching-candidates.spec.ts",
  reporter: [
    ["list"],
    [
      "json",
      {
        outputFile: "../docs/phase-12/generic-candidates-browser-results.json",
      },
    ],
  ],
});
