import { defineConfig } from "@playwright/test";
import base from "./playwright.country-workflows.config";
export default defineConfig({
  ...base,
  testMatch: "bank-account-scope.spec.ts",
  reporter: [
    ["list"],
    [
      "json",
      {
        outputFile: "../docs/phase-12/bank-account-scope-browser-results.json",
      },
    ],
  ],
});
