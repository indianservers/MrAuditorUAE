# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: qa-crud.spec.ts >> working paper actual form creates a persisted draft
- Location: e2e\qa-crud.spec.ts:126:1

# Error details

```
TimeoutError: locator.fill: Timeout 20000ms exceeded.
Call log:
  - waiting for getByLabel(/^Folder/)

```

# Page snapshot

```yaml
- generic [ref=f2e1]:
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
          - option "SYNTHETIC CRUD دبي CRUD-1792311362540"
          - option "SYNTHETIC role probe Firm Administrator"
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
        - combobox "Select entity" [disabled] [ref=f2e18]:
          - option "Select entity" [selected]
        - combobox "Select period" [disabled] [ref=f2e20]:
          - option "Select period" [selected]
      - button "Notifications" [ref=f2e21] [cursor=pointer]
      - button "User menu" [ref=f2e25] [cursor=pointer]:
        - generic [ref=f2e26]: QA
        - generic [ref=f2e27]:
          - text: qa.admin@auditos.example
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
              - text: Engagement / External audit
              - generic [ref=f2e202]: ›
              - text: Working Paper Editor
            - heading "Working Paper Editor" [level=1] [ref=f2e203]
            - paragraph [ref=f2e204]: QA FICTIONAL 01 General Trading External Audit
          - generic [ref=f2e205]:
            - generic [ref=f2e206]: draft
            - button "New record" [ref=f2e207] [cursor=pointer]
        - navigation "Engagement workspaces" [ref=f2e209]:
          - link "Engagement Acceptance" [ref=f2e210] [cursor=pointer]:
            - /url: /engagements/e6294f99-575c-4f20-98c9-efb00094fd57/acceptance
          - link "Independence & Ethics" [ref=f2e211] [cursor=pointer]:
            - /url: /engagements/e6294f99-575c-4f20-98c9-efb00094fd57/independence
          - link "Audit Planning Studio" [ref=f2e212] [cursor=pointer]:
            - /url: /engagements/e6294f99-575c-4f20-98c9-efb00094fd57/planning
          - link "Materiality Calculator" [ref=f2e213] [cursor=pointer]:
            - /url: /engagements/e6294f99-575c-4f20-98c9-efb00094fd57/materiality
          - link "Risk & Assertions Matrix" [ref=f2e214] [cursor=pointer]:
            - /url: /engagements/e6294f99-575c-4f20-98c9-efb00094fd57/risks
          - link "Audit Program Builder" [ref=f2e215] [cursor=pointer]:
            - /url: /engagements/e6294f99-575c-4f20-98c9-efb00094fd57/programs
          - link "Procedure Assignments" [ref=f2e216] [cursor=pointer]:
            - /url: /engagements/e6294f99-575c-4f20-98c9-efb00094fd57/procedures
          - link "Audit Testing Workbench" [ref=f2e217] [cursor=pointer]:
            - /url: /engagements/e6294f99-575c-4f20-98c9-efb00094fd57/testing
          - link "Working Paper Editor" [ref=f2e218] [cursor=pointer]:
            - /url: /engagements/e6294f99-575c-4f20-98c9-efb00094fd57/working-papers
          - link "Evidence Review Studio" [ref=f2e219] [cursor=pointer]:
            - /url: /engagements/e6294f99-575c-4f20-98c9-efb00094fd57/evidence
          - link "Findings & Misstatements" [ref=f2e220] [cursor=pointer]:
            - /url: /engagements/e6294f99-575c-4f20-98c9-efb00094fd57/findings
          - link "Reviewer Command Center" [ref=f2e221] [cursor=pointer]:
            - /url: /engagements/e6294f99-575c-4f20-98c9-efb00094fd57/review-notes
          - link "Engagement Completion" [ref=f2e222] [cursor=pointer]:
            - /url: /engagements/e6294f99-575c-4f20-98c9-efb00094fd57/completion
          - link "Client Document Requests" [ref=f2e223] [cursor=pointer]:
            - /url: /engagements/e6294f99-575c-4f20-98c9-efb00094fd57/requests
          - link "Engagement AI Assistant" [ref=f2e224] [cursor=pointer]:
            - /url: /engagements/e6294f99-575c-4f20-98c9-efb00094fd57/ai
          - link "Engagement Team" [ref=f2e225] [cursor=pointer]:
            - /url: /engagements/e6294f99-575c-4f20-98c9-efb00094fd57/team
        - generic [ref=f2e226]:
          - text: Record lifecycle filter
          - combobox "Record lifecycle filter" [ref=f2e227]:
            - option "Current records" [selected]
            - option "Archived drafts"
        - generic [ref=f2e228]:
          - generic [ref=f2e229]: Human review required
          - generic [ref=f2e233]: 0 linked audit records
          - generic [ref=f2e234]: Versioned • Tenant isolated • Source linked
        - generic [ref=f2e235]:
          - region "Audit record register" [ref=f2e236]:
            - generic [ref=f2e237]:
              - textbox "Search audit records" [ref=f2e238]:
                - /placeholder: Search reference or title…
              - generic [ref=f2e239]: 0 records
              - button "Refresh" [ref=f2e240] [cursor=pointer]
            - generic [ref=f2e241]:
              - generic [ref=f2e242]:
                - generic [ref=f2e243]: Sort & filter loaded records · Community grid
                - generic [ref=f2e244]:
                  - button "Columns" [ref=f2e245] [cursor=pointer]
                  - button "Compact" [ref=f2e248] [cursor=pointer]
                  - button "Save view" [ref=f2e251] [cursor=pointer]
                  - button "Reset grid view" [ref=f2e256] [cursor=pointer]
                  - button "CSV · page" [disabled] [ref=f2e260]
              - status [ref=f2e264]
              - generic [ref=f2e269]:
                - generic [ref=f2e270]: Loading...
                - grid [ref=f2e271]:
                  - rowgroup [ref=f2e272]:
                    - row [ref=f2e273]:
                      - columnheader [ref=f2e274]
                      - columnheader "Reference" [ref=f2e275]:
                        - generic [aria-hidden] [ref=f2e277] [cursor=pointer]
                      - columnheader "Audit record" [ref=f2e279]:
                        - generic [aria-hidden] [ref=f2e281] [cursor=pointer]
                      - columnheader "Review status" [ref=f2e283]:
                        - generic [aria-hidden] [ref=f2e285] [cursor=pointer]
                      - columnheader "Version" [ref=f2e287]:
                        - generic [aria-hidden] [ref=f2e289] [cursor=pointer]
                      - columnheader "Last updated" [ref=f2e291]:
                        - generic [aria-hidden] [ref=f2e293] [cursor=pointer]
                - generic: No records in this context
              - generic [ref=f2e295]: Import or select a financial population to begin. No demonstration figures are substituted.
            - generic [ref=f2e296]:
              - generic [ref=f2e297]: 0 records
              - generic [ref=f2e298]:
                - button "Previous page" [disabled] [ref=f2e299]: Previous
                - generic [ref=f2e300]: Page 1
                - button "Next page" [disabled] [ref=f2e301]: Next
              - generic [ref=f2e302]: Server page · 50 rows
            - group [ref=f2e303]:
              - generic "Engagement lifecycle" [ref=f2e304] [cursor=pointer]
          - complementary "Audit record editor" [ref=f2e309]:
            - strong [ref=f2e315]: Prepare new record
            - group [ref=f2e318]:
              - generic [ref=f2e319]:
                - generic [ref=f2e320]:
                  - text: Reference
                  - textbox "Reference" [ref=f2e321]:
                    - /placeholder: e.g. PL-001
                    - text: CRUD-PAPER-1792311367848
                - generic [ref=f2e322]:
                  - text: Title
                  - textbox "Title" [active] [ref=f2e323]: SYNTHETIC browser lifecycle paper
              - generic [ref=f2e324]:
                - generic [ref=f2e325]: folder *
                - textbox "folder required" [ref=f2e326]
              - generic [ref=f2e327]:
                - generic [ref=f2e328]: sections *
                - generic [ref=f2e329]:
                  - generic [ref=f2e330]:
                    - textbox "Section 1 heading" [ref=f2e331]: Objective and work performed
                    - textbox "Section 1 text" [ref=f2e332]
                  - button "Add section" [ref=f2e333] [cursor=pointer]
              - generic [ref=f2e334]:
                - generic [ref=f2e335]: conclusion *
                - textbox "conclusion required" [ref=f2e336]
              - generic [ref=f2e337]:
                - generic [ref=f2e338]: narrative
                - textbox "narrative" [ref=f2e339]
              - generic [ref=f2e340]:
                - generic [ref=f2e341]: sources
                - generic [ref=f2e342]:
                  - combobox "Link source record" [ref=f2e343]:
                    - option "Choose engagement source…" [selected]
                    - option "Snapshot â€” 9fef4f74"
                    - option "Snapshot â€” f964c5a7"
                    - option "Snapshot â€” 2f680180"
                    - option "Sample â€” a56f3812"
                    - option "Finding â€” J01"
                    - option "Finding â€” J01"
                    - option "Finding â€” J01"
                    - option "Finding â€” J01"
                    - option "Finding â€” J01"
                    - option "Finding â€” J01"
                    - option "Finding â€” J01"
                    - option "Finding â€” J01"
                    - option "Finding â€” J01"
                    - option "Finding â€” J01"
                    - option "Finding â€” J01"
                    - option "Finding â€” J01"
                    - option "Finding â€” J01"
                    - option "Finding â€” J01"
                    - option "Finding â€” J01"
                    - option "Journal â€” 33a3e74e"
                    - option "Journal â€” c2c7f116"
                    - option "Journal â€” cc9690d2"
                    - option "Journal â€” 11c7cc90"
                    - option "Journal â€” 2ca200fb"
                    - option "Journal â€” f8a38b2b"
                    - option "Journal â€” ae557f93"
                    - option "Journal â€” 2f86b497"
                    - option "Journal â€” c5ed9aff"
                    - option "Journal â€” 3e67b9f6"
                    - option "Journal â€” 2ddb04a8"
                    - option "Journal â€” 2e25493d"
                    - option "Journal â€” c429970f"
                    - option "Journal â€” 06d21288"
                    - option "Journal â€” f5e59a1f"
                  - group [ref=f2e344]:
                    - generic "Advanced source references" [ref=f2e345] [cursor=pointer]
              - generic [ref=f2e346]:
                - generic [ref=f2e347]: owner id
                - textbox "owner id" [ref=f2e348]:
                  - /placeholder: UUID
              - generic [ref=f2e349]:
                - generic [ref=f2e350]: due date
                - textbox "due date" [ref=f2e351]
              - generic [ref=f2e352]:
                - generic [ref=f2e353]: area
                - textbox "area" [ref=f2e354]
              - generic [ref=f2e355]:
                - generic [ref=f2e356]: assertions
                - generic [ref=f2e357]:
                  - generic [ref=f2e358]:
                    - checkbox "existence" [ref=f2e359]
                    - text: existence
                  - generic [ref=f2e360]:
                    - checkbox "completeness" [ref=f2e361]
                    - text: completeness
                  - generic [ref=f2e362]:
                    - checkbox "accuracy" [ref=f2e363]
                    - text: accuracy
                  - generic [ref=f2e364]:
                    - checkbox "valuation" [ref=f2e365]
                    - text: valuation
                  - generic [ref=f2e366]:
                    - checkbox "rights and obligations" [ref=f2e367]
                    - text: rights and obligations
                  - generic [ref=f2e368]:
                    - checkbox "occurrence" [ref=f2e369]
                    - text: occurrence
                  - generic [ref=f2e370]:
                    - checkbox "cut off" [ref=f2e371]
                    - text: cut off
                  - generic [ref=f2e372]:
                    - checkbox "classification" [ref=f2e373]
                    - text: classification
                  - generic [ref=f2e374]:
                    - checkbox "presentation" [ref=f2e375]
                    - text: presentation
              - generic [ref=f2e376]:
                - generic [ref=f2e377]: financial tables
                - textbox "financial tables" [ref=f2e378]:
                  - /placeholder: "[]"
                  - text: "[]"
              - button "Save version" [ref=f2e379] [cursor=pointer]
```

# Test source

```ts
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
  80  |     await form.getByRole("combobox", {name: "status", exact: true}).selectOption(status);
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
> 139 |   await page.getByLabel(/^Folder/).fill("Planning");
      |                                    ^ TimeoutError: locator.fill: Timeout 20000ms exceeded.
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
  176 |   expect(created.status()).toBe(201); const row = await created.json();
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