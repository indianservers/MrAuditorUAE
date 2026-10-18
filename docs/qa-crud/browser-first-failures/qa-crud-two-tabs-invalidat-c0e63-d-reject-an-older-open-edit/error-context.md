# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: qa-crud.spec.ts >> two tabs invalidate cached grids and reject an older open edit
- Location: e2e\qa-crud.spec.ts:171:1

# Error details

```
Error: expect(received).toBe(expected) // Object.is equality

Expected: 201
Received: 403
```

# Page snapshot

```yaml
- generic [active] [ref=f1e1]:
  - alert [ref=f1e2]
  - generic [ref=f1e3]:
    - banner [ref=f1e4]:
      - link "A AuditOS UAE" [ref=f1e5] [cursor=pointer]:
        - /url: /dashboard
        - generic [ref=f1e6]: A
        - generic [ref=f1e7]: AuditOS UAE
      - button "Search accounts, transactions, clients, or ask AI… ⌘ K" [ref=f1e8] [cursor=pointer]:
        - generic [ref=f1e12]: Search accounts, transactions, clients, or ask AI…
        - generic [ref=f1e13]: ⌘ K
      - generic [ref=f1e14]:
        - combobox "Select client" [ref=f1e16]:
          - option "Firm-wide" [selected]
          - option "SYNTHETIC CRUD دبي CRUD-1792311215530"
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
        - combobox "Select entity" [disabled] [ref=f1e18]:
          - option "Select entity" [selected]
        - combobox "Select period" [disabled] [ref=f1e20]:
          - option "Select period" [selected]
      - button "Notifications" [ref=f1e21] [cursor=pointer]
      - button "User menu" [ref=f1e25] [cursor=pointer]:
        - generic [ref=f1e26]: QA
        - generic [ref=f1e27]:
          - text: qa.admin@auditos.example
          - generic [ref=f1e28]: Firm workspace
    - complementary [ref=f1e31]:
      - button "Collapse navigation" [ref=f1e32] [cursor=pointer]:
        - generic [ref=f1e36]: Workspace
      - navigation "Main navigation" [ref=f1e40]:
        - link "AI Providers" [ref=f1e42] [cursor=pointer]:
          - /url: /ai/providers
        - link "AI Command Center" [ref=f1e48] [cursor=pointer]:
          - /url: /ai/command-center
        - link "Internal Audit & GRC" [ref=f1e54] [cursor=pointer]:
          - /url: /grc
        - link "Board Portal" [ref=f1e60] [cursor=pointer]:
          - /url: /board
        - link "Audit ML Lab" [ref=f1e65] [cursor=pointer]:
          - /url: /ai-lab
        - link "Pillar Two" [ref=f1e71] [cursor=pointer]:
          - /url: /pillar-two
        - link "Transfer Pricing" [ref=f1e76] [cursor=pointer]:
          - /url: /tp
        - link "VAT & E-Invoicing" [ref=f1e83] [cursor=pointer]:
          - /url: /vat
        - link "IFRS Reporting" [ref=f1e91] [cursor=pointer]:
          - /url: /ifrs
        - button "Firm Administration" [ref=f1e97] [cursor=pointer]
        - link "Dashboard" [ref=f1e107] [cursor=pointer]:
          - /url: /dashboard
        - link "Clients" [ref=f1e115] [cursor=pointer]:
          - /url: /clients
        - link "Engagements" [ref=f1e123] [cursor=pointer]:
          - /url: /engagements
        - link "Integrations" [ref=f1e129] [cursor=pointer]:
          - /url: /integrations
        - button "Financial Data" [ref=f1e134] [cursor=pointer]
        - button "Audit Intelligence" [ref=f1e141] [cursor=pointer]
        - link "Evidence" [ref=f1e151] [cursor=pointer]:
          - /url: /evidence
        - link "AI Copilot" [ref=f1e158] [cursor=pointer]:
          - /url: /ai-copilot
        - link "Corporate Tax" [ref=f1e164] [cursor=pointer]:
          - /url: /tax
        - link "Compliance" [ref=f1e171] [cursor=pointer]:
          - /url: /compliance
        - link "Reports" [ref=f1e177] [cursor=pointer]:
          - /url: /reports
        - link "Settings" [ref=f1e183] [cursor=pointer]:
          - /url: /settings
      - generic [ref=f1e188]:
        - link "AI Assistant Investigate your financial data. Context aware" [ref=f1e189] [cursor=pointer]:
          - /url: /ai-copilot
          - strong [ref=f1e193]: AI Assistant
          - generic [ref=f1e194]: Investigate your financial data.
          - generic [ref=f1e195]: Context aware
        - generic [ref=f1e196]: AuditOS Precision · v0.3
    - main [ref=f1e197]:
      - generic [ref=f1e198]:
        - generic [ref=f1e199]:
          - generic [ref=f1e200]:
            - generic [ref=f1e201]:
              - text: Firm overview
              - generic [ref=f1e202]: ›
              - text: Executive Dashboard
            - heading "Executive Dashboard" [level=1] [ref=f1e203]
            - paragraph [ref=f1e204]: Your authorized portfolio, financial exceptions and recent firm activity.
          - generic [ref=f1e205]: Live backend records
        - generic [ref=f1e207]:
          - generic [ref=f1e208]:
            - generic [ref=f1e209]: Portfolio overview
            - combobox "Engagement status filter" [ref=f1e210]:
              - option "All engagement statuses" [selected]
              - option "draft"
              - option "active"
              - option "completed"
              - option "cancelled"
          - generic [ref=f1e211]:
            - link "Total Clients 27" [ref=f1e212] [cursor=pointer]:
              - /url: /clients
              - generic [ref=f1e219]:
                - generic [ref=f1e220]: Total Clients
                - strong [ref=f1e221]: "27"
            - link "Active Engagements 0" [ref=f1e225] [cursor=pointer]:
              - /url: /engagements
              - generic [ref=f1e230]:
                - generic [ref=f1e231]: Active Engagements
                - strong [ref=f1e232]: "0"
            - link "Stored Review Findings 56,489" [ref=f1e236] [cursor=pointer]:
              - /url: /audit/risk-intelligence
              - generic [ref=f1e240]:
                - generic [ref=f1e241]: Stored Review Findings
                - strong [ref=f1e242]: 56,489
            - link "Compliance Deadlines Not configured" [ref=f1e246] [cursor=pointer]:
              - /url: /compliance
              - generic [ref=f1e252]:
                - generic [ref=f1e253]: Compliance Deadlines
                - strong [ref=f1e254]: Not configured
          - generic [ref=f1e258]:
            - generic [ref=f1e259]:
              - generic [ref=f1e260]:
                - heading "Engagement Overview" [level=3] [ref=f1e261]
                - link "View all" [ref=f1e262] [cursor=pointer]:
                  - /url: /engagements
              - generic [ref=f1e266]:
                - link "QA workflow 22 External Audit draft" [ref=f1e267] [cursor=pointer]:
                  - /url: /engagements/183de79f-21ce-4ffa-a471-097f4d7cb78a
                  - generic [ref=f1e272]:
                    - strong [ref=f1e273]: QA workflow 22
                    - generic [ref=f1e274]: External Audit
                  - generic [ref=f1e275]: draft
                - link "QA workflow 18 External Audit draft" [ref=f1e279] [cursor=pointer]:
                  - /url: /engagements/829f5c71-cea0-437f-ac17-3d22e1c2a1dd
                  - generic [ref=f1e284]:
                    - strong [ref=f1e285]: QA workflow 18
                    - generic [ref=f1e286]: External Audit
                  - generic [ref=f1e287]: draft
                - link "QA workflow 21 External Audit draft" [ref=f1e291] [cursor=pointer]:
                  - /url: /engagements/24916597-74fc-479d-b817-f25831c1a693
                  - generic [ref=f1e296]:
                    - strong [ref=f1e297]: QA workflow 21
                    - generic [ref=f1e298]: External Audit
                  - generic [ref=f1e299]: draft
                - link "QA workflow 17 External Audit draft" [ref=f1e303] [cursor=pointer]:
                  - /url: /engagements/871285d7-7d46-407e-b9d7-7404e3760331
                  - generic [ref=f1e308]:
                    - strong [ref=f1e309]: QA workflow 17
                    - generic [ref=f1e310]: External Audit
                  - generic [ref=f1e311]: draft
                - link "QA workflow 16 External Audit draft" [ref=f1e315] [cursor=pointer]:
                  - /url: /engagements/7acfe2c6-f731-45d7-b9b0-66ffeba6065f
                  - generic [ref=f1e320]:
                    - strong [ref=f1e321]: QA workflow 16
                    - generic [ref=f1e322]: External Audit
                  - generic [ref=f1e323]: draft
                - link "QA workflow 14 External Audit draft" [ref=f1e327] [cursor=pointer]:
                  - /url: /engagements/2cea4264-ebde-4290-ab15-1a8c75eae69d
                  - generic [ref=f1e332]:
                    - strong [ref=f1e333]: QA workflow 14
                    - generic [ref=f1e334]: External Audit
                  - generic [ref=f1e335]: draft
                - link "QA workflow 13 External Audit draft" [ref=f1e339] [cursor=pointer]:
                  - /url: /engagements/52c28d1b-5639-4fbc-aeee-15b85b08a080
                  - generic [ref=f1e344]:
                    - strong [ref=f1e345]: QA workflow 13
                    - generic [ref=f1e346]: External Audit
                  - generic [ref=f1e347]: draft
                - link "QA workflow 12 External Audit draft" [ref=f1e351] [cursor=pointer]:
                  - /url: /engagements/053a48c1-0d9a-4dde-bc41-a84e3c7da70b
                  - generic [ref=f1e356]:
                    - strong [ref=f1e357]: QA workflow 12
                    - generic [ref=f1e358]: External Audit
                  - generic [ref=f1e359]: draft
              - paragraph [ref=f1e363]: Professional audit program progress is available in Phase 4.
            - generic [ref=f1e364]:
              - heading "Financial Intelligence" [level=3] [ref=f1e365]
              - link [ref=f1e369] [cursor=pointer]:
                - /url: /audit/risk-intelligence
                - generic [ref=f1e371]:
                  - strong [ref=f1e372]: Investigate deterministic findings
                  - paragraph [ref=f1e373]: 56489 stored rule exceptions across runs. Repeated runs may flag the same item.
              - link [ref=f1e377] [cursor=pointer]:
                - /url: /financials/reconciliation
                - generic [ref=f1e379]:
                  - strong [ref=f1e380]: Verify financial completeness
                  - paragraph [ref=f1e381]: Inspect source controls, balance checks and independent reconciliation evidence.
              - link [ref=f1e385] [cursor=pointer]:
                - /url: /ai-copilot
                - generic [ref=f1e387]:
                  - strong [ref=f1e388]: Request contextual AI support
                  - paragraph [ref=f1e389]: Structured, cited suggestions using the approved AI gateway.
          - generic [ref=f1e393]:
            - generic [ref=f1e394]:
              - heading "Recent Firm Activity" [level=3] [ref=f1e395]
              - generic [ref=f1e396]:
                - generic [ref=f1e397]:
                  - strong [ref=f1e401]: clients · created
                  - generic [ref=f1e402]: 10/18/2026, 1:43:36 PM
                - generic [ref=f1e403]:
                  - strong [ref=f1e407]: clients · created
                  - generic [ref=f1e408]: 10/18/2026, 1:37:15 PM
                - generic [ref=f1e409]:
                  - strong [ref=f1e413]: accounting · activated
                  - generic [ref=f1e414]: 10/18/2026, 1:12:09 PM
                - generic [ref=f1e415]:
                  - strong [ref=f1e419]: accounting · validated
                  - generic [ref=f1e420]: 10/18/2026, 1:12:09 PM
                - generic [ref=f1e421]:
                  - strong [ref=f1e425]: accounting · uploaded
                  - generic [ref=f1e426]: 10/18/2026, 1:12:09 PM
                - generic [ref=f1e427]:
                  - strong [ref=f1e431]: mapping · version_created
                  - generic [ref=f1e432]: 10/18/2026, 1:12:09 PM
                - generic [ref=f1e433]:
                  - strong [ref=f1e437]: accounting · activated
                  - generic [ref=f1e438]: 10/18/2026, 1:12:08 PM
                - generic [ref=f1e439]:
                  - strong [ref=f1e443]: accounting · validated
                  - generic [ref=f1e444]: 10/18/2026, 1:12:08 PM
            - generic [ref=f1e445]:
              - heading "Compliance Status" [level=3] [ref=f1e446]
              - generic [ref=f1e447]:
                - heading "Not yet configured" [level=3] [ref=f1e453]
                - paragraph [ref=f1e454]: Corporate Tax, VAT, Transfer Pricing and Pillar Two services are available in Phase 5. No deadlines or compliance ratings are inferred.
              - link "Open Compliance Command Center" [ref=f1e455] [cursor=pointer]:
                - /url: /compliance
```

# Test source

```ts
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
  103 |     headers: { "Origin": "http://127.0.0.1:3006", "X-Tenant-ID": data.tenant_id },
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
  138 |     .fill("SYNTHETIC browser lifecycle paper");
  139 |   await page.getByLabel(/^Folder/).fill("Planning");
  140 |   await page.getByRole("button", { name: "Add section" }).click();
  141 |   await page.getByLabel("Section 1 heading").fill("Objective");
  142 |   await page
  143 |     .getByLabel("Section 1 text")
  144 |     .fill("Synthetic browser evidence without production data");
  145 |   await page
  146 |     .getByLabel(/^Conclusion/)
  147 |     .fill("Synthetic draft conclusion for controlled review");
  148 |   const save = page.waitForResponse(
  149 |     (r) =>
  150 |       r.url().includes("/audit/working-papers") &&
  151 |       r.request().method() === "POST",
  152 |   );
  153 |   await page.getByRole("button", { name: "Save version" }).click();
  154 |   const response = await save;
  155 |   expect(response.status()).toBe(201);
  156 |   const row = await response.json();
  157 |   const get = await page.request.get(
  158 |     `/api/backend/engagements/${eid}/audit/records/${row.id}`,
  159 |     { headers: { "Origin": "http://127.0.0.1:3006", "X-Tenant-ID": data.tenant_id } },
  160 |   );
  161 |   expect(get.status()).toBe(200);
  162 |   expect((await get.json()).body.conclusion).toContain(
  163 |     "Synthetic draft conclusion",
  164 |   );
  165 |   await page.screenshot({
  166 |     path: "../docs/qa-crud/screenshots/working-paper-created.png",
  167 |     fullPage: true,
  168 |   });
  169 | });
  170 | 
  171 | test("two tabs invalidate cached grids and reject an older open edit", async ({page, context}) => {
  172 |   await login(page);
  173 |   const code = `CRUD-RACE-${Date.now()}`;
  174 |   const headers = {"Origin": "http://127.0.0.1:3006", "X-Tenant-ID": data.tenant_id};
  175 |   const created = await page.request.post("/api/backend/clients", {headers, data: {code, name: "SYNTHETIC concurrent draft"}});
> 176 |   expect(created.status()).toBe(201); const row = await created.json();
      |                            ^ Error: expect(received).toBe(expected) // Object.is equality
  177 |   const second = await context.newPage();
  178 |   for (const tab of [page, second]) {
  179 |     await tab.goto("/clients"); await tab.getByLabel("Search clients").fill(code);
  180 |     await tab.locator(".ag-cell strong").filter({hasText: "SYNTHETIC concurrent draft"}).click();
  181 |     await tab.getByRole("button", {name: "Edit client", exact: true}).click();
  182 |   }
  183 |   const firstForm = page.getByRole("dialog", {name: "Edit client", exact: true});
  184 |   await firstForm.getByLabel("name", {exact: true}).fill("SYNTHETIC first editor persisted");
  185 |   const saved = page.waitForResponse(r => r.url().includes(row.id) && r.request().method() === "PATCH");
  186 |   await firstForm.getByRole("button", {name: "Save client"}).click(); expect((await saved).status()).toBe(200);
  187 |   const secondForm = second.getByRole("dialog", {name: "Edit client", exact: true});
  188 |   await secondForm.getByLabel("name", {exact: true}).fill("SYNTHETIC stale editor overwrite");
  189 |   const conflict = second.waitForResponse(r => r.url().includes(row.id) && r.request().method() === "PATCH");
  190 |   await secondForm.getByRole("button", {name: "Save client"}).click(); expect((await conflict).status()).toBe(409);
  191 |   await expect(secondForm.getByRole("alert")).toContainText("version conflict");
  192 |   await second.screenshot({path: "../docs/qa-crud/screenshots/concurrent-edit-conflict.png", fullPage: true});
  193 |   await secondForm.getByRole("button", {name: "Close dialog"}).click();
  194 |   await expect(second.locator(".ag-cell strong").filter({hasText: "SYNTHETIC first editor persisted"})).toBeVisible();
  195 |   const persisted = await page.request.get(`/api/backend/clients/${row.id}`, {headers});
  196 |   expect((await persisted.json()).name).toBe("SYNTHETIC first editor persisted");
  197 |   await second.close();
  198 | });
  199 | 
```