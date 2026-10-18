# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: qa-crud.spec.ts >> client form create edit archive restore with separate persisted API assertions
- Location: e2e\qa-crud.spec.ts:47:1

# Error details

```
TimeoutError: locator.selectOption: Timeout 20000ms exceeded.
Call log:
  - waiting for getByRole('dialog', { name: 'Edit client', exact: true }).getByLabel('status', { exact: true })

```

# Page snapshot

```yaml
- generic:
  - alert
  - generic:
    - banner [aria-hidden]:
      - link:
        - /url: /dashboard
        - generic: A
        - generic: AuditOS UAE
      - button:
        - generic: Search accounts, transactions, clients, or ask AI…
        - generic: ⌘ K
      - generic:
        - generic:
          - combobox
        - generic:
          - combobox [disabled]
        - generic:
          - combobox [disabled]
      - button
      - button:
        - generic: QA
        - generic:
          - text: qa.admin@auditos.example
          - generic: Firm workspace
    - complementary [aria-hidden]:
      - button:
        - generic: Workspace
      - navigation:
        - generic:
          - link:
            - /url: /ai/providers
            - generic: AI Providers
        - generic:
          - link:
            - /url: /ai/command-center
            - generic: AI Command Center
        - generic:
          - link:
            - /url: /grc
            - generic: Internal Audit & GRC
        - generic:
          - link:
            - /url: /board
            - generic: Board Portal
        - generic:
          - link:
            - /url: /ai-lab
            - generic: Audit ML Lab
        - generic:
          - link:
            - /url: /pillar-two
            - generic: Pillar Two
        - generic:
          - link:
            - /url: /tp
            - generic: Transfer Pricing
        - generic:
          - link:
            - /url: /vat
            - generic: VAT & E-Invoicing
        - generic:
          - link:
            - /url: /ifrs
            - generic: IFRS Reporting
        - generic:
          - button:
            - generic: Firm Administration
        - generic:
          - link:
            - /url: /dashboard
            - generic: Dashboard
        - generic:
          - link:
            - /url: /clients
            - generic: Clients
        - generic:
          - link:
            - /url: /engagements
            - generic: Engagements
        - generic:
          - link:
            - /url: /integrations
            - generic: Integrations
        - generic:
          - button:
            - generic: Financial Data
        - generic:
          - button:
            - generic: Audit Intelligence
        - generic:
          - link:
            - /url: /evidence
            - generic: Evidence
        - generic:
          - link:
            - /url: /ai-copilot
            - generic: AI Copilot
        - generic:
          - link:
            - /url: /tax
            - generic: Corporate Tax
        - generic:
          - link:
            - /url: /compliance
            - generic: Compliance
        - generic:
          - link:
            - /url: /reports
            - generic: Reports
        - generic:
          - link:
            - /url: /settings
            - generic: Settings
      - generic:
        - link:
          - /url: /ai-copilot
          - strong: AI Assistant
          - generic: Investigate your financial data.
          - generic: Context aware
        - generic: AuditOS Precision · v0.3
    - main:
      - generic:
        - generic [aria-hidden]:
          - generic:
            - generic:
              - text: Firm workspace
              - generic: ›
              - text: Client & Company Management
            - heading [level=1]: Client & Company Management
            - paragraph: Manage your client portfolio, legal entities and engagements.
          - generic:
            - button: Add client
        - generic:
          - generic [aria-hidden]:
            - generic: All clients 1
            - generic: Authorized firm directory
          - generic [aria-hidden]:
            - generic:
              - textbox:
                - /placeholder: Search clients by name or code…
                - text: CRUD-1792311215530
            - combobox
            - generic: "Tax IDs, industry and deadlines: not configured"
          - generic:
            - generic [aria-hidden]:
              - generic: Sort & filter loaded records · Community grid
              - generic:
                - button: Columns
                - button: Compact
                - button: Save view
                - button
                - button: CSV · page
            - status [aria-hidden]
            - generic:
              - generic:
                - generic:
                  - generic:
                    - generic:
                      - generic: Loading.... Press SPACE to deselect this row
                      - generic [aria-hidden]:
                        - grid:
                          - rowgroup:
                            - row:
                              - columnheader
                              - columnheader:
                                - generic: Client code
                              - columnheader:
                                - generic: Client / company
                              - columnheader:
                                - generic: Client type
                              - columnheader:
                                - generic: Status
                              - columnheader:
                                - generic: Last activity
                              - columnheader:
                                - generic: Version
                            - row [selected]:
                              - gridcell:
                                - checkbox [checked]
                              - gridcell: CRUD-1792311215530
                              - gridcell:
                                - generic:
                                  - strong: SYNTHETIC CRUD دبي CRUD-1792311215530
                              - gridcell: company
                              - gridcell:
                                - generic: active
                              - gridcell: 10/18/2026, 1:43:36 PM
                              - gridcell: "1"
          - generic [aria-hidden]:
            - generic: 1–1 of 1 records
            - generic:
              - button [disabled]: Previous
              - generic: Page 1
              - button [disabled]: Next
            - generic: Server page · 50 rows
  - dialog [ref=f2e2]:
    - banner [ref=f2e3]:
      - heading "Edit client" [level=2] [ref=f2e4]
      - button "Close dialog" [active] [ref=f2e5] [cursor=pointer]
    - generic [ref=f2e9]:
      - generic [ref=f2e10]:
        - text: code
        - textbox "code" [disabled] [ref=f2e11]: CRUD-1792311215530
      - generic [ref=f2e13]:
        - text: name
        - textbox "name" [ref=f2e14]: SYNTHETIC CRUD دبي CRUD-1792311215530
      - generic [ref=f2e16]:
        - text: kind
        - combobox "kind" [disabled] [ref=f2e17]:
          - option "company" [selected]
          - option "group"
          - option "individual"
      - generic [ref=f2e19]:
        - text: status
        - combobox "status" [ref=f2e20]:
          - option "active" [selected]
          - option "inactive"
          - option "archived"
      - generic [ref=f2e22]:
        - text: Lifecycle reason
        - textbox "Lifecycle reason" [ref=f2e23]:
          - /placeholder: Required when archiving or restoring this client
      - button "Save client" [ref=f2e24] [cursor=pointer]
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
  37  |     expect(create.status()).toBe(permissions[role].includes("clients.write") ? 201 : 403);
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
> 80  |     await form.getByLabel("status", { exact: true }).selectOption(status);
      |                                                      ^ TimeoutError: locator.selectOption: Timeout 20000ms exceeded.
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
  138 |     .fill("SYNTHETIC browser lifecycle paper");
  139 |   await page.getByLabel("Folder", { exact: true }).fill("Planning");
  140 |   await page.getByRole("button", { name: "Add section" }).click();
  141 |   await page.getByLabel("Section 1 heading").fill("Objective");
  142 |   await page
  143 |     .getByLabel("Section 1 text")
  144 |     .fill("Synthetic browser evidence without production data");
  145 |   await page
  146 |     .getByLabel("Conclusion", { exact: true })
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
  159 |     { headers: { "X-Tenant-ID": data.tenant_id } },
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
  174 |   const headers = {"X-Tenant-ID": data.tenant_id};
  175 |   const created = await page.request.post("/api/backend/clients", {headers, data: {code, name: "SYNTHETIC concurrent draft"}});
  176 |   expect(created.status()).toBe(201); const row = await created.json();
  177 |   const second = await context.newPage();
  178 |   for (const tab of [page, second]) {
  179 |     await tab.goto("/clients"); await tab.getByLabel("Search clients").fill(code);
  180 |     await tab.locator(".ag-cell strong").filter({hasText: "SYNTHETIC concurrent draft"}).click();
```