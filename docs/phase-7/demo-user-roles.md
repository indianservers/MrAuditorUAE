# Demo User Roles

- `synthetic.user00@auditos.test` — Platform Super Admin
- `synthetic.user01@auditos.test` — Firm Administrator
- `synthetic.user02@auditos.test` — Managing Partner
- `synthetic.user03@auditos.test` — Chartered Accountant
- `synthetic.user04@auditos.test` — Audit Manager
- `synthetic.user05@auditos.test` — Senior Auditor
- `synthetic.user06@auditos.test` — Auditor
- `synthetic.user07@auditos.test` — Audit Trainee
- `synthetic.user08@auditos.test` — Tax Director
- `synthetic.user09@auditos.test` — Tax Manager
- `synthetic.user10@auditos.test` — Tax Consultant
- `synthetic.user11@auditos.test` — Financial Reporting Manager
- `synthetic.user12@auditos.test` — Consolidation Specialist
- `synthetic.user13@auditos.test` — Quality Reviewer
- `synthetic.user14@auditos.test` — Client Administrator
- `synthetic.user15@auditos.test` — Client Finance Manager
- `synthetic.user16@auditos.test` — Client Accountant
- `synthetic.user17@auditos.test` — Client Document Contributor
- `synthetic.user18@auditos.test` — Client Viewer
- `synthetic.user19@auditos.test` — Read-only Reviewer
- `synthetic.user20@auditos.test` — VAT Analyst
- `synthetic.user21@auditos.test` — VAT Manager
- `synthetic.user22@auditos.test` — VAT Read-only Reviewer
- `synthetic.user23@auditos.test` — Auditor; expired engagement grant
- `synthetic.user24@auditos.test` — Auditor; disabled

The CA has an additional Audit Partner role for final independent review. Tax Consultant user10 also has Senior Tax Consultant membership and engagement grants on FY2026 for the reviewed QFZP scenarios; the base Tax Consultant role alone does not grant CT preparation. Client users are restricted to client1 portal records and receive no confidential VAT/audit access. VAT read-only reviewer cannot prepare or export. Platform Super Admin has no confidential tenant bypass. Expired and disabled fixtures are intentionally denied.

Passwords are supplied by PHASE7_DEMO_PASSWORD; no shared fixed password is committed. This local run generated a random development password in ignored `.local-runtime/phase7/demo-login.local.json`. All addresses use `.test`. Do not reuse these identities or identifiers in production. `demo-verification.json` records actual25-user VAT access responses; this is not a claim that every action was exhaustively tested for every role.

- `synthetic.accountant@auditos.test` — Accountant [SYNTHETIC DEMO], limited internal accounting import/read role, separate from restricted Client Accountant. Actual four-line FY2027 QA import/validate/commit/TB executed. This signed-balance QA example is independent of the normal30 annual financial fixtures. No audit, VAT approval, user administration or client portal grants.

Auditor user06 additionally holds Audit Analytics [SYNTHETIC DEMO] for explicit accounting/analytics access in this isolated tenant. VAT Analyst user20 additionally holds Invoice Validator with an engagement grant. CA user03 has an explicit Audit Partner engagement grant on the first FY2026 scenario; the CA's self-prepared paper still awaits a different final partner. These fixture grants do not broaden the application's default Auditor or Client Accountant roles.
