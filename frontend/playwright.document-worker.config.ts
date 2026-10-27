import { defineConfig } from "@playwright/test";
import base from "./playwright.country-workflows.config";
export default defineConfig({
  ...base,
  testMatch: "document-worker.spec.ts",
  reporter: [
    ["list"],
    [
      "json",
      {
        outputFile: "../docs/phase-12/document-worker-browser-results.json",
      },
    ],
  ],
});
