import { defineConfig } from "@playwright/test";
import base from "./playwright.country-workflows.config";
export default defineConfig({
  ...base,
  testMatch: "adverse-media.spec.ts",
  reporter: [
    ["list"],
    [
      "json",
      { outputFile: "../docs/phase-12/adverse-media-browser-results.json" },
    ],
  ],
});
