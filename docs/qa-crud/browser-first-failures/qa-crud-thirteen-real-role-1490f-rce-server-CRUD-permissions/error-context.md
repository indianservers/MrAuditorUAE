# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: qa-crud.spec.ts >> thirteen real role logins enforce server CRUD permissions
- Location: e2e\qa-crud.spec.ts:19:1

# Error details

```
Error: expect(received).toBe(expected) // Object.is equality

Expected: 201
Received: 403
```

# Page snapshot

```yaml
- generic [active] [ref=f2e1]:
  - alert [ref=f2e2]
  - generic [ref=f2e3]:
    - banner [ref=f2e4]:
      - link "A AuditOS UAE" [ref=f2e5] [cursor=pointer]:
        - /url: /dashboard
        - generic [ref=f2e6]: A
        - generic [ref=f2e7]: AuditOS UAE
      - button "Search accounts, transactions, clients, or ask AI… ⌘ K" [ref=f2e8] [cursor=pointer]:
        - generic [ref=f2e12]: Search accounts, transactions, clients, or ask AI…
        - generic [ref=f2e13]: ⌘ K
      - generic [ref=f2e14]:
        - combobox "Select client" [ref=f2e16]:
          - option "Firm-wide" [selected]
          - option "SYNTHETIC CRUD دبي CRUD-1792310834231"
          - option "QA FICTIONAL 25 Joint Venture"
          - option "QA FICTIONAL 24 Foreign Subsidiary"
          - option "QA FICTIONAL 23 Free Zone"
          - option "QA FICTIONAL 22 Holding"
          - option "QA FICTIONAL 21 Retail"
          - option "QA FICTIONAL 20 IT Services"
          - option "QA FICTIONAL 19 Logistics"
          - option "QA FICTIONAL 18 Manufacturing"
          - option "QA FICTIONAL 17 Professional Services"
          - option "QA FICTIONAL 16 Financial Services"
          - option "QA FICTIONAL 15 International Trading"
          - option "QA FICTIONAL 14 Free Zone"
          - option "QA FICTIONAL 13 Holding"
          - option "QA FICTIONAL 12 Education"
          - option "QA FICTIONAL 11 Healthcare"
          - option "QA FICTIONAL 10 Retail"
          - option "QA FICTIONAL 09 Hospitality"
          - option "QA FICTIONAL 08 Property Development"
          - option "QA FICTIONAL 07 Property Investment"
          - option "QA FICTIONAL 06 Construction"
          - option "QA FICTIONAL 05 Consulting"
          - option "QA FICTIONAL 04 IT Services"
          - option "QA FICTIONAL 03 Logistics"
          - option "QA FICTIONAL 02 Manufacturing"
          - option "QA FICTIONAL 01 General Trading"
        - combobox "Select entity" [disabled] [ref=f2e18]:
          - option "Select entity" [selected]
        - combobox "Select period" [disabled] [ref=f2e20]:
          - option "Select period" [selected]
      - button "Notifications" [ref=f2e21] [cursor=pointer]
      - button "User menu" [ref=f2e25] [cursor=pointer]:
        - generic [ref=f2e26]: QA
        - generic [ref=f2e27]:
          - text: qa.role01@auditos.example
          - generic [ref=f2e28]: Firm workspace
    - complementary [ref=f2e31]:
      - button "Collapse navigation" [ref=f2e32] [cursor=pointer]:
        - generic [ref=f2e36]: Workspace
      - navigation "Main navigation" [ref=f2e40]:
        - link "AI Providers" [ref=f2e42] [cursor=pointer]:
          - /url: /ai/providers
        - link "AI Command Center" [ref=f2e48] [cursor=pointer]:
          - /url: /ai/command-center
        - link "Internal Audit & GRC" [ref=f2e54] [cursor=pointer]:
          - /url: /grc
        - link "Board Portal" [ref=f2e60] [cursor=pointer]:
          - /url: /board
        - link "Audit ML Lab" [ref=f2e65] [cursor=pointer]:
          - /url: /ai-lab
        - link "Pillar Two" [ref=f2e71] [cursor=pointer]:
          - /url: /pillar-two
        - link "Transfer Pricing" [ref=f2e76] [cursor=pointer]:
          - /url: /tp
        - link "VAT & E-Invoicing" [ref=f2e83] [cursor=pointer]:
          - /url: /vat
        - link "IFRS Reporting" [ref=f2e91] [cursor=pointer]:
          - /url: /ifrs
        - button "Firm Administration" [ref=f2e97] [cursor=pointer]
        - link "Dashboard" [ref=f2e107] [cursor=pointer]:
          - /url: /dashboard
        - link "Clients" [ref=f2e115] [cursor=pointer]:
          - /url: /clients
        - link "Engagements" [ref=f2e123] [cursor=pointer]:
          - /url: /engagements
        - link "Integrations" [ref=f2e129] [cursor=pointer]:
          - /url: /integrations
        - button "Financial Data" [ref=f2e134] [cursor=pointer]
        - button "Audit Intelligence" [ref=f2e141] [cursor=pointer]
        - link "Evidence" [ref=f2e151] [cursor=pointer]:
          - /url: /evidence
        - link "AI Copilot" [ref=f2e158] [cursor=pointer]:
          - /url: /ai-copilot
        - link "Corporate Tax" [ref=f2e164] [cursor=pointer]:
          - /url: /tax
        - link "Compliance" [ref=f2e171] [cursor=pointer]:
          - /url: /compliance
        - link "Reports" [ref=f2e177] [cursor=pointer]:
          - /url: /reports
        - link "Settings" [ref=f2e183] [cursor=pointer]:
          - /url: /settings
      - generic [ref=f2e188]:
        - link "AI Assistant Investigate your financial data. Context aware" [ref=f2e189] [cursor=pointer]:
          - /url: /ai-copilot
          - strong [ref=f2e193]: AI Assistant
          - generic [ref=f2e194]: Investigate your financial data.
          - generic [ref=f2e195]: Context aware
        - generic [ref=f2e196]: AuditOS Precision · v0.3
    - main [ref=f2e197]:
      - generic [ref=f2e198]:
        - generic [ref=f2e199]:
          - generic [ref=f2e200]:
            - generic [ref=f2e201]:
              - text: Firm workspace
              - generic [ref=f2e202]: ›
              - text: Client & Company Management
            - heading "Client & Company Management" [level=1] [ref=f2e203]
            - paragraph [ref=f2e204]: Manage your client portfolio, legal entities and engagements.
          - button "Add client" [ref=f2e206] [cursor=pointer]
        - generic [ref=f2e208]:
          - generic [ref=f2e209]:
            - generic [ref=f2e210]: All clients 26
            - generic [ref=f2e211]: Authorized firm directory
          - generic [ref=f2e212]:
            - textbox "Search clients" [ref=f2e217]:
              - /placeholder: Search clients by name or code…
            - combobox "Client status filter" [ref=f2e218]:
              - option "Current clients" [selected]
              - option "active"
              - option "inactive"
              - option "archived"
            - generic [ref=f2e219]: "Tax IDs, industry and deadlines: not configured"
          - generic [ref=f2e220]:
            - generic [ref=f2e221]:
              - generic [ref=f2e222]: Sort & filter loaded records · Community grid
              - generic [ref=f2e223]:
                - button "Columns" [ref=f2e224] [cursor=pointer]
                - button "Compact" [ref=f2e227] [cursor=pointer]
                - button "Save view" [ref=f2e230] [cursor=pointer]
                - button "Reset grid view" [ref=f2e235] [cursor=pointer]
                - button "CSV · page" [ref=f2e239] [cursor=pointer]
            - status [ref=f2e243]
            - grid [ref=f2e250]:
              - rowgroup [ref=f2e251]:
                - row [ref=f2e252]:
                  - columnheader [ref=f2e253]
                  - columnheader "Client code" [ref=f2e254]:
                    - generic [aria-hidden] [ref=f2e256] [cursor=pointer]
                  - columnheader "Client / company" [ref=f2e258]:
                    - generic [aria-hidden] [ref=f2e260] [cursor=pointer]
                  - columnheader "Client type" [ref=f2e262]:
                    - generic [aria-hidden] [ref=f2e264] [cursor=pointer]
                  - columnheader "Status" [ref=f2e266]:
                    - generic [aria-hidden] [ref=f2e268] [cursor=pointer]
                  - columnheader "Last activity" [ref=f2e270]:
                    - generic [aria-hidden] [ref=f2e272] [cursor=pointer]
                  - columnheader "Version" [ref=f2e274]:
                    - generic [aria-hidden] [ref=f2e276] [cursor=pointer]
                - row [ref=f2e278]:
                  - gridcell [ref=f2e279]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e280] [cursor=pointer]
                  - gridcell "CRUD-1792310834231" [ref=f2e281]
                  - gridcell [ref=f2e282]:
                    - strong [ref=f2e287]: SYNTHETIC CRUD دبي CRUD-1792310834231
                  - gridcell "company" [ref=f2e288]
                  - gridcell "active" [ref=f2e289]
                  - gridcell "10/18/2026, 1:37:15 PM" [ref=f2e291]
                  - gridcell "1" [ref=f2e292]
                - row [ref=f2e293]:
                  - gridcell [ref=f2e294]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e295] [cursor=pointer]
                  - gridcell "QA-25" [ref=f2e296]
                  - gridcell [ref=f2e297]:
                    - strong [ref=f2e303]: QA FICTIONAL 25 Joint Venture
                  - gridcell "company" [ref=f2e304]
                  - gridcell "active" [ref=f2e305]
                  - gridcell "10/18/2026, 12:35:13 PM" [ref=f2e307]
                  - gridcell "1" [ref=f2e308]
                - row [ref=f2e309]:
                  - gridcell [ref=f2e310]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e311] [cursor=pointer]
                  - gridcell "QA-24" [ref=f2e312]
                  - gridcell [ref=f2e313]:
                    - strong [ref=f2e319]: QA FICTIONAL 24 Foreign Subsidiary
                  - gridcell "company" [ref=f2e320]
                  - gridcell "active" [ref=f2e321]
                  - gridcell "10/18/2026, 12:35:13 PM" [ref=f2e323]
                  - gridcell "1" [ref=f2e324]
                - row [ref=f2e325]:
                  - gridcell [ref=f2e326]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e327] [cursor=pointer]
                  - gridcell "QA-23" [ref=f2e328]
                  - gridcell [ref=f2e329]:
                    - strong [ref=f2e335]: QA FICTIONAL 23 Free Zone
                  - gridcell "company" [ref=f2e336]
                  - gridcell "active" [ref=f2e337]
                  - gridcell "10/18/2026, 12:35:12 PM" [ref=f2e339]
                  - gridcell "1" [ref=f2e340]
                - row [ref=f2e341]:
                  - gridcell [ref=f2e342]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e343] [cursor=pointer]
                  - gridcell "QA-22" [ref=f2e344]
                  - gridcell [ref=f2e345]:
                    - strong [ref=f2e351]: QA FICTIONAL 22 Holding
                  - gridcell "company" [ref=f2e352]
                  - gridcell "active" [ref=f2e353]
                  - gridcell "10/18/2026, 12:35:12 PM" [ref=f2e355]
                  - gridcell "1" [ref=f2e356]
                - row [ref=f2e357]:
                  - gridcell [ref=f2e358]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e359] [cursor=pointer]
                  - gridcell "QA-21" [ref=f2e360]
                  - gridcell [ref=f2e361]:
                    - strong [ref=f2e367]: QA FICTIONAL 21 Retail
                  - gridcell "company" [ref=f2e368]
                  - gridcell "active" [ref=f2e369]
                  - gridcell "10/18/2026, 12:35:12 PM" [ref=f2e371]
                  - gridcell "1" [ref=f2e372]
                - row [ref=f2e373]:
                  - gridcell [ref=f2e374]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e375] [cursor=pointer]
                  - gridcell "QA-20" [ref=f2e376]
                  - gridcell [ref=f2e377]:
                    - strong [ref=f2e383]: QA FICTIONAL 20 IT Services
                  - gridcell "company" [ref=f2e384]
                  - gridcell "active" [ref=f2e385]
                  - gridcell "10/18/2026, 12:35:12 PM" [ref=f2e387]
                  - gridcell "1" [ref=f2e388]
                - row [ref=f2e389]:
                  - gridcell [ref=f2e390]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e391] [cursor=pointer]
                  - gridcell "QA-19" [ref=f2e392]
                  - gridcell [ref=f2e393]:
                    - strong [ref=f2e399]: QA FICTIONAL 19 Logistics
                  - gridcell "company" [ref=f2e400]
                  - gridcell "active" [ref=f2e401]
                  - gridcell "10/18/2026, 12:35:12 PM" [ref=f2e403]
                  - gridcell "1" [ref=f2e404]
                - row [ref=f2e405]:
                  - gridcell [ref=f2e406]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e407] [cursor=pointer]
                  - gridcell "QA-18" [ref=f2e408]
                  - gridcell [ref=f2e409]:
                    - strong [ref=f2e415]: QA FICTIONAL 18 Manufacturing
                  - gridcell "company" [ref=f2e416]
                  - gridcell "active" [ref=f2e417]
                  - gridcell "10/18/2026, 12:35:12 PM" [ref=f2e419]
                  - gridcell "1" [ref=f2e420]
                - row [ref=f2e421]:
                  - gridcell [ref=f2e422]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e423] [cursor=pointer]
                  - gridcell "QA-17" [ref=f2e424]
                  - gridcell [ref=f2e425]:
                    - strong [ref=f2e431]: QA FICTIONAL 17 Professional Services
                  - gridcell "company" [ref=f2e432]
                  - gridcell "active" [ref=f2e433]
                  - gridcell "10/18/2026, 12:35:12 PM" [ref=f2e435]
                  - gridcell "1" [ref=f2e436]
                - row [ref=f2e437]:
                  - gridcell [ref=f2e438]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e439] [cursor=pointer]
                  - gridcell "QA-16" [ref=f2e440]
                  - gridcell [ref=f2e441]:
                    - strong [ref=f2e447]: QA FICTIONAL 16 Financial Services
                  - gridcell "company" [ref=f2e448]
                  - gridcell "active" [ref=f2e449]
                  - gridcell "10/18/2026, 12:35:11 PM" [ref=f2e451]
                  - gridcell "1" [ref=f2e452]
                - row [ref=f2e453]:
                  - gridcell [ref=f2e454]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e455] [cursor=pointer]
                  - gridcell "QA-15" [ref=f2e456]
                  - gridcell [ref=f2e457]:
                    - strong [ref=f2e463]: QA FICTIONAL 15 International Trading
                  - gridcell "company" [ref=f2e464]
                  - gridcell "active" [ref=f2e465]
                  - gridcell "10/18/2026, 12:35:11 PM" [ref=f2e467]
                  - gridcell "1" [ref=f2e468]
                - row [ref=f2e469]:
                  - gridcell [ref=f2e470]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e471] [cursor=pointer]
                  - gridcell "QA-14" [ref=f2e472]
                  - gridcell [ref=f2e473]:
                    - strong [ref=f2e479]: QA FICTIONAL 14 Free Zone
                  - gridcell "company" [ref=f2e480]
                  - gridcell "active" [ref=f2e481]
                  - gridcell "10/18/2026, 12:35:11 PM" [ref=f2e483]
                  - gridcell "1" [ref=f2e484]
                - row [ref=f2e485]:
                  - gridcell [ref=f2e486]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e487] [cursor=pointer]
                  - gridcell "QA-13" [ref=f2e488]
                  - gridcell [ref=f2e489]:
                    - strong [ref=f2e495]: QA FICTIONAL 13 Holding
                  - gridcell "company" [ref=f2e496]
                  - gridcell "active" [ref=f2e497]
                  - gridcell "10/18/2026, 12:35:11 PM" [ref=f2e499]
                  - gridcell "1" [ref=f2e500]
                - row [ref=f2e501]:
                  - gridcell [ref=f2e502]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e503] [cursor=pointer]
                  - gridcell "QA-12" [ref=f2e504]
                  - gridcell [ref=f2e505]:
                    - strong [ref=f2e511]: QA FICTIONAL 12 Education
                  - gridcell "company" [ref=f2e512]
                  - gridcell "active" [ref=f2e513]
                  - gridcell "10/18/2026, 12:35:11 PM" [ref=f2e515]
                  - gridcell "1" [ref=f2e516]
                - row [ref=f2e517]:
                  - gridcell [ref=f2e518]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e519] [cursor=pointer]
                  - gridcell "QA-11" [ref=f2e520]
                  - gridcell [ref=f2e521]:
                    - strong [ref=f2e527]: QA FICTIONAL 11 Healthcare
                  - gridcell "company" [ref=f2e528]
                  - gridcell "active" [ref=f2e529]
                  - gridcell "10/18/2026, 12:35:11 PM" [ref=f2e531]
                  - gridcell "1" [ref=f2e532]
                - row [ref=f2e533]:
                  - gridcell [ref=f2e534]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e535] [cursor=pointer]
                  - gridcell "QA-10" [ref=f2e536]
                  - gridcell [ref=f2e537]:
                    - strong [ref=f2e543]: QA FICTIONAL 10 Retail
                  - gridcell "company" [ref=f2e544]
                  - gridcell "active" [ref=f2e545]
                  - gridcell "10/18/2026, 12:35:11 PM" [ref=f2e547]
                  - gridcell "1" [ref=f2e548]
                - row [ref=f2e549]:
                  - gridcell [ref=f2e550]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e551] [cursor=pointer]
                  - gridcell "QA-09" [ref=f2e552]
                  - gridcell [ref=f2e553]:
                    - strong [ref=f2e559]: QA FICTIONAL 09 Hospitality
                  - gridcell "company" [ref=f2e560]
                  - gridcell "active" [ref=f2e561]
                  - gridcell "10/18/2026, 12:35:11 PM" [ref=f2e563]
                  - gridcell "1" [ref=f2e564]
                - row [ref=f2e565]:
                  - gridcell [ref=f2e566]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e567] [cursor=pointer]
                  - gridcell "QA-08" [ref=f2e568]
                  - gridcell [ref=f2e569]:
                    - strong [ref=f2e575]: QA FICTIONAL 08 Property Development
                  - gridcell "company" [ref=f2e576]
                  - gridcell "active" [ref=f2e577]
                  - gridcell "10/18/2026, 12:35:11 PM" [ref=f2e579]
                  - gridcell "1" [ref=f2e580]
                - row [ref=f2e581]:
                  - gridcell [ref=f2e582]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e583] [cursor=pointer]
                  - gridcell "QA-07" [ref=f2e584]
                  - gridcell [ref=f2e585]:
                    - strong [ref=f2e591]: QA FICTIONAL 07 Property Investment
                  - gridcell "company" [ref=f2e592]
                  - gridcell "active" [ref=f2e593]
                  - gridcell "10/18/2026, 12:35:11 PM" [ref=f2e595]
                  - gridcell "1" [ref=f2e596]
                - row [ref=f2e597]:
                  - gridcell [ref=f2e598]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e599] [cursor=pointer]
                  - gridcell "QA-06" [ref=f2e600]
                  - gridcell [ref=f2e601]:
                    - strong [ref=f2e607]: QA FICTIONAL 06 Construction
                  - gridcell "company" [ref=f2e608]
                  - gridcell "active" [ref=f2e609]
                  - gridcell "10/18/2026, 12:35:10 PM" [ref=f2e611]
                  - gridcell "1" [ref=f2e612]
                - row [ref=f2e613]:
                  - gridcell [ref=f2e614]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e615] [cursor=pointer]
                  - gridcell "QA-05" [ref=f2e616]
                  - gridcell [ref=f2e617]:
                    - strong [ref=f2e623]: QA FICTIONAL 05 Consulting
                  - gridcell "company" [ref=f2e624]
                  - gridcell "active" [ref=f2e625]
                  - gridcell "10/18/2026, 12:35:10 PM" [ref=f2e627]
                  - gridcell "1" [ref=f2e628]
                - row [ref=f2e629]:
                  - gridcell [ref=f2e630]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e631] [cursor=pointer]
                  - gridcell "QA-04" [ref=f2e632]
                  - gridcell [ref=f2e633]:
                    - strong [ref=f2e639]: QA FICTIONAL 04 IT Services
                  - gridcell "company" [ref=f2e640]
                  - gridcell "active" [ref=f2e641]
                  - gridcell "10/18/2026, 12:35:10 PM" [ref=f2e643]
                  - gridcell "1" [ref=f2e644]
                - row [ref=f2e645]:
                  - gridcell [ref=f2e646]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e647] [cursor=pointer]
                  - gridcell "QA-03" [ref=f2e648]
                  - gridcell [ref=f2e649]:
                    - strong [ref=f2e655]: QA FICTIONAL 03 Logistics
                  - gridcell "company" [ref=f2e656]
                  - gridcell "active" [ref=f2e657]
                  - gridcell "10/18/2026, 12:35:10 PM" [ref=f2e659]
                  - gridcell "1" [ref=f2e660]
                - row [ref=f2e661]:
                  - gridcell [ref=f2e662]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e663] [cursor=pointer]
                  - gridcell "QA-02" [ref=f2e664]
                  - gridcell [ref=f2e665]:
                    - strong [ref=f2e671]: QA FICTIONAL 02 Manufacturing
                  - gridcell "company" [ref=f2e672]
                  - gridcell "active" [ref=f2e673]
                  - gridcell "10/18/2026, 12:35:10 PM" [ref=f2e675]
                  - gridcell "1" [ref=f2e676]
                - row [ref=f2e677]:
                  - gridcell [ref=f2e678]:
                    - checkbox "Press Space to toggle row selection (unchecked)" [ref=f2e679] [cursor=pointer]
                  - gridcell "QA-01" [ref=f2e680]
                  - gridcell [ref=f2e681]:
                    - strong [ref=f2e687]: QA FICTIONAL 01 General Trading
                  - gridcell "company" [ref=f2e688]
                  - gridcell "active" [ref=f2e689]
                  - gridcell "10/18/2026, 12:35:10 PM" [ref=f2e691]
                  - gridcell "1" [ref=f2e692]
          - generic [ref=f2e695]:
            - generic [ref=f2e696]: 1–26 of 26 records
            - generic [ref=f2e697]:
              - button "Previous page" [disabled] [ref=f2e698]: Previous
              - generic [ref=f2e699]: Page 1
              - button "Next page" [disabled] [ref=f2e700]: Next
            - generic [ref=f2e701]: Server page · 50 rows
```

# Test source

```ts
  1   | import { test, expect, Page } from "@playwright/test";
  2   | import { readFileSync, writeFileSync } from "node:fs";
  3   | const credentials = JSON.parse(
  4   |   readFileSync("../.local-runtime/qa-campaign/environment.local.json", "utf8"),
  5   | );
  6   | const data = JSON.parse(
  7   |   readFileSync("../docs/qa-campaign/dataset.json", "utf8"),
  8   | );
  9   | async function login(page: Page) {
  10  |   await page.goto("/login");
  11  |   await page.getByLabel("Email address").fill("qa.admin@auditos.example");
  12  |   await page
  13  |     .getByLabel("Password", { exact: true })
  14  |     .fill(credentials.QA_PASSWORD);
  15  |   await page.getByRole("button", { name: "Sign in", exact: true }).click();
  16  |   await page.waitForURL("**/dashboard");
  17  | }
  18  | 
  19  | test("thirteen real role logins enforce server CRUD permissions", async ({browser}) => {
  20  |   test.setTimeout(240000);
  21  |   const roles = ["Platform Administrator", "Firm Administrator", "Audit Partner / Chartered Accountant", "Audit Manager", "Auditor", "Tax Manager", "TP Analyst", "VAT Analyst", "Internal Auditor", "Client Administrator", "Client Viewer", "Quality Reviewer", "Read-only Reviewer"];
  22  |   const permissions = JSON.parse(readFileSync("../docs/qa-campaign/inventory.json", "utf8")).roles;
  23  |   const receipts = [];
  24  |   for (const role of roles) {
  25  |     const user = data.users.find((u: {role: string}) => u.role === role);
  26  |     const context = await browser.newContext(); const page = await context.newPage();
  27  |     await page.goto("/login");
  28  |     await page.getByLabel("Email address").fill(user.email);
  29  |     await page.getByLabel("Password", {exact:true}).fill(credentials.QA_PASSWORD);
  30  |     await page.getByRole("button", {name:"Sign in",exact:true}).click();
  31  |     await page.waitForURL("**/dashboard");
  32  |     await page.goto("/clients");
  33  |     const headers = {"X-Tenant-ID": data.tenant_id};
  34  |     const read = await page.request.get("/api/backend/clients?limit=1", {headers});
  35  |     expect(read.status()).toBe(permissions[role].includes("clients.read") ? 200 : 403);
  36  |     const create = await page.request.post("/api/backend/clients", {headers, data:{code:`CRUD-ROLE-${roles.indexOf(role)}-${Date.now()}`,name:`SYNTHETIC role probe ${role}`}});
> 37  |     expect(create.status()).toBe(permissions[role].includes("clients.write") ? 201 : 403);
      |                             ^ Error: expect(received).toBe(expected) // Object.is equality
  38  |     const cross = await page.request.get("/api/backend/clients", {headers:{"X-Tenant-ID":"00000000-0000-4000-8000-000000000001"}});
  39  |     expect(cross.status()).toBe(403);
  40  |     receipts.push({role, read:read.status(), create:create.status(), crossTenant:cross.status(), scope:"Real login and client CRUD authorization; specialist form workflow not covered by this probe"});
  41  |     await page.screenshot({path:`../docs/qa-crud/screenshots/role-${roles.indexOf(role)}.png`,fullPage:true});
  42  |     writeFileSync("../docs/qa-crud/browser-role-results.json",JSON.stringify(receipts,null,2));
  43  |     await context.close();
  44  |     await new Promise(resolve => setTimeout(resolve,3500));
  45  |   }
  46  | });
  47  | test("client form create edit archive restore with separate persisted API assertions", async ({
  48  |   page,
  49  | }) => {
  50  |   await login(page);
  51  |   await page.goto("/clients");
  52  |   const code = `CRUD-${Date.now()}`;
  53  |   const name = `SYNTHETIC CRUD دبي ${code}`;
  54  |   await page.getByRole("button", { name: "Add client" }).click();
  55  |   const dialog = page.getByRole("dialog").last();
  56  |   await dialog.getByLabel("code", { exact: true }).fill(code);
  57  |   await dialog.getByLabel("name", { exact: true }).fill(name);
  58  |   const created = page.waitForResponse(
  59  |     (r) =>
  60  |       r.url().endsWith("/api/backend/clients") &&
  61  |       r.request().method() === "POST",
  62  |   );
  63  |   await dialog.getByRole("button", { name: "Save client" }).click();
  64  |   const result = await created;
  65  |   expect(result.status()).toBe(201);
  66  |   const row = await result.json();
  67  |   await page.getByLabel("Search clients").fill(code);
  68  |   const cell = page.locator(".ag-cell strong").filter({ hasText: name });
  69  |   await expect(cell).toBeVisible();
  70  |   await page.screenshot({
  71  |     path: "../docs/qa-crud/screenshots/client-created.png",
  72  |     fullPage: true,
  73  |   });
  74  |   for (const status of ["archived", "active"]) {
  75  |     await cell.click();
  76  |     await page
  77  |       .getByRole("button", { name: "Edit client", exact: true })
  78  |       .click();
  79  |     const form = page.getByRole("dialog", {name: "Edit client", exact: true});
  80  |     await form.getByLabel("status", { exact: true }).selectOption(status);
  81  |     await form
  82  |       .getByLabel("Lifecycle reason")
  83  |       .fill(`Synthetic browser lifecycle review for ${status}`);
  84  |     const saved = page.waitForResponse(
  85  |       (r) =>
  86  |         r.url().includes(`/api/backend/clients/${row.id}`) &&
  87  |         r.request().method() === "PATCH",
  88  |     );
  89  |     await form.getByRole("button", { name: "Save client" }).click();
  90  |     expect((await saved).status()).toBe(200);
  91  |     await expect(cell).toHaveCount(0);
  92  |     await page.getByLabel("Client status filter").selectOption(status);
  93  |     await expect(cell).toBeVisible();
  94  |     await page.screenshot({
  95  |       path: `../docs/qa-crud/screenshots/client-${status}.png`,
  96  |       fullPage: true,
  97  |     });
  98  |   }
  99  |   await page.reload();
  100 |   await page.getByLabel("Search clients").fill(code);
  101 |   await expect(cell).toBeVisible();
  102 |   const persisted = await page.request.get(`/api/backend/clients/${row.id}`, {
  103 |     headers: { "X-Tenant-ID": data.tenant_id },
  104 |   });
  105 |   expect(persisted.status()).toBe(200);
  106 |   const final = await persisted.json();
  107 |   expect(final.status).toBe("active");
  108 |   expect(final.version).toBe(row.version + 2);
  109 |   expect(final.name).toBe(name);
  110 |   writeFileSync(
  111 |     "../docs/qa-crud/browser-client-receipt.json",
  112 |     JSON.stringify(
  113 |       {
  114 |         id: row.id,
  115 |         code,
  116 |         initialVersion: row.version,
  117 |         finalVersion: final.version,
  118 |         status: final.status,
  119 |       },
  120 |       null,
  121 |       2,
  122 |     ),
  123 |   );
  124 | });
  125 | 
  126 | test("working paper actual form creates a persisted draft", async ({
  127 |   page,
  128 | }) => {
  129 |   await login(page);
  130 |   const eid = data.companies[0].engagements[0].id;
  131 |   await page.goto(`/engagements/${eid}/working-papers`);
  132 |   await page.getByRole("button", { name: "New record" }).click();
  133 |   await page
  134 |     .getByLabel("Reference", { exact: true })
  135 |     .fill(`CRUD-PAPER-${Date.now()}`);
  136 |   await page
  137 |     .getByLabel("Title", { exact: true })
```