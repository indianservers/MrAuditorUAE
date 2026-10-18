# Accounting reconciliation

All committed scale batches passed real API trial-balance balanced checks. At each scale checkpoint independent SQL sums matched debits/credits and exact committed scale batch counts.

[
  {
    "target": 10000,
    "actual": 10000,
    "debit": "25126728.82000000",
    "credit": "25126728.82000000",
    "seconds": 10.188999899997725,
    "passed": true
  },
  {
    "target": 100000,
    "actual": 100000,
    "debit": "250623385.90000000",
    "credit": "250623385.90000000",
    "seconds": 110.74600099999952,
    "passed": true
  },
  {
    "target": 250000,
    "actual": 250000,
    "debit": "626471489.12000000",
    "credit": "626471489.12000000",
    "seconds": 161.0813116000063,
    "passed": true
  },
  {
    "target": 500000,
    "actual": 500000,
    "debit": "1252939723.21000000",
    "credit": "1252939723.21000000",
    "seconds": 0.676429699997243,
    "passed": true
  },
  {
    "target": 1000000,
    "actual": 1000000,
    "debit": "2505854207.95000000",
    "credit": "2505854207.95000000",
    "seconds": 444.66338659999747,
    "passed": true
  }
]

See dataset.json and financial-results.json. Full entity/year TB snapshots are separate populations; no unapproved merge or overwrite is performed. Opening/movement/closing is independently exercised by fixed Decimal fixtures.
