# Sample Data Inventory

- clients: 10
- entities: 10
- engagements: 30
- journal_lines: 250,024
- samples: 60
- financial_periods: 31
- chart_accounts: 250
- users: 26
- analytics_runs: 4
- vat-invoice: 5,001
- working-papers: 152
- findings: 60
- procedures: 120
- evidence: 121

25 base synthetic users plus1 internal Accountant;30 base financial periods plus1 isolated FY2027 QA period;250 chart accounts;5,000 approved synthetic invoice sources plus1 deliberately defective draft;121 evidence records including1 real portal PDF upload. Ten FY2026 approved IFRS statement/CT scenarios, ten alternative QFZP profiles/assessments, five IFRS specialist workpapers/runs (lease/ECL/revenue/deferred tax/fixed assets).30 VAT reconciliations and60 sampling runs were generated. Four actual analytics runs are recorded in the manifest. Requests and negative fixtures are additional review data, not financial totals.

- SYNTHETIC — Al Noor Trading LLC
- SYNTHETIC — Emirates Tech Solutions LLC
- SYNTHETIC — Gulf Horizon Properties LLC
- SYNTHETIC — Desert Logistics FZCO
- SYNTHETIC — Crescent Manufacturing LLC
- SYNTHETIC — Pearl Hospitality LLC
- SYNTHETIC — Falcon Consulting LLC
- SYNTHETIC — BlueWave International FZCO
- SYNTHETIC — Meridian Investment Holding LLC
- SYNTHETIC — Oasis Retail LLC

Exact IDs, expected balances, benchmark timings, approved source snapshots and specialist IDs are in `demo-manifest.json`. The seed's primary record-count replay verifies thresholds and records totals; `verify_demo.py` performs the independent GL checks. QFZP profiles are alternative synthetic scenarios, not additive financial entities. Persistent consolidation/intercompany numerical scenarios are not included; the existing automated consolidation tests were executed.
