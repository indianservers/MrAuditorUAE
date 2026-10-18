import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir:"./e2e", testMatch:/phase(?:7|8|9|10|11|12)\.spec\.ts/,
  workers:1, timeout:240000, expect:{timeout:25000},
  reporter:[["list"],["json",{outputFile:"../docs/phase-12/browser-results.json"}]],
  use:{baseURL:process.env.AUDITOS_E2E_ORIGIN||"http://127.0.0.1:3004",viewport:{width:1600,height:900},reducedMotion:"reduce",trace:"retain-on-failure",screenshot:"only-on-failure"},
});
