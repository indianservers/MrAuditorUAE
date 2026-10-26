import { defineConfig } from "@playwright/test";
import base from "./playwright.country-workflows.config";
export default defineConfig({
  ...base,
  testMatch: "grant-utilisation.spec.ts",
  reporter: [
    ["list"],
    [
      "json",
      { outputFile: "../docs/phase-12/grant-utilisation-browser-results.json" },
    ],
  ],
});
