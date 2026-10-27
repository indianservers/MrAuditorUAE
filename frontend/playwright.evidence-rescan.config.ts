import { defineConfig } from "@playwright/test";
import base from "./playwright.country-workflows.config";
export default defineConfig({
  ...base,
  testMatch: "evidence-rescan.spec.ts",
  reporter: [
    ["list"],
    ["json", { outputFile: "../docs/phase-12/evidence-rescan-browser.json" }],
  ],
});
