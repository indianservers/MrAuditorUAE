# Processor reserve continuity and ledger controls

`merchant-reserve-rollforward` is available for UAE and India engagements. It
reuses a reviewed processor settlement source from `merchant-settlement-bridge`.
It connects separately reported reserve holds and releases to opening and closing
processor balances, then to independently retained receivable ledger controls.
The original payout workflow continues to assess booked bank allocations.

## Required evidence

Select four different, current, independently reviewed source versions:

- `settlements / merchant-settlements`: the original processor batches with all
  nine independent component controls. The country and assessed fee-tax labels
  must agree with the engagement. This workflow supplies no statutory rates.
- `movements / merchant-reserve-movements`: original hold/release records, exact
  settlement-row IDs, merchant, processor, currency, date and explicit sequence
  within that day's statement chronology. Include original references, retained
  evidence references and an assessment. Amounts are positive; kind is `HELD` or
  `RELEASED`. Independent held and released totals remain separate.
- `balances / merchant-reserve-balances`: explicit opening and closing balances
  for each merchant/processor/currency position, period dates, an assessed
  receivable ledger account mapping and retained evidence reference. Separate
  independent opening and closing totals are required, including assessed zeros.
- `ledger / balance-controls`: original nonnegative receivable balances for each
  declared account, dated the day before the reporting period and the closing
  reconciliation date. Missing controls remain unknown rather than zero.

The source screen provides individual currency and amount inputs for reserve
controls. They start blank. For API uploads, use `merchant_reserve_controls`:

```json
{"AED":{"held":"50","released":"5"}}
```

For balance sources use `opening_balance` and `closing_balance` instead. Generic
`control_totals` must be empty for these two tables: adding holds to releases or
opening to closing would conceal their distinct meanings. The existing processor
and ledger source contracts retain their own original monetary controls.

## Calculation and review

Select an explicit reporting period and one currency. UAE and India share the
reserve arithmetic and evidence controls; processor country/fee-tax assessments
remain country-specific. INR and AED are not converted or pooled. Date and amount
tolerances are zero.

For every original payout batch, dated movement totals must equal the separate
`reserve_held` and `reserve_released` components. The processor gross-to-net
arithmetic is checked again. Missing offsetting holds and releases cannot pass
because their net happens to match.

For each position, calculate opening plus holds minus releases in declared
date/sequence order. A release exceeding available reserves blocks approval even
if a later hold restores the final balance. Funds cannot be borrowed from another
merchant's position, including positions that share a ledger account. Position
closings must match the supplied processor balance. Position openings and closings
are then aggregated only within the assessed ledger account and original currency
and compared with both dated GL controls.

Duplicate movement IDs, repeated original same-kind references and ambiguous
chronology positions are rejected. Unknown batches, party/currency mismatches and
out-of-period movement dates are rejected. A missing position or ledger point,
component difference, arithmetic difference, negative interim reserve or balance
difference blocks independent approval. The preparer cannot approve their result.

Withdrawing a source review makes dependent results stale without rewriting their
saved financial rows. Recalculate using the revised evidence before approval.
Results missing `dated-merchant-reserve-ledger/1` require regeneration.

## Export and limits

The result retains every original movement, batch, balance and GL source ID.
XLSX adds **Reserve movements** and **Reserve balance links** sheets so large
populations are individual records rather than a long JSON cell. The main Rows
sheet points to those complete details; the saved result remains unchanged.

This comparison does not authenticate a processor, prove bank receipt, establish
legal ownership or recoverability, calculate impairment, FX or tax recovery, issue
a journal or payment instruction, or reserve cash across workflows. The separate
bank workflow retains its own document-link and authentication limits. Source
completeness, opening balance validity, original statement chronology and account
mapping still require an independent human assessment. Synthetic examples and
automated tests do not qualify actual clients or legal cohorts.

## Retained verification

On application commit `9ba08d4`, local validation passed 3,203 backend unit tests
(five skipped), four focused database/API workflows and 307 frontend tests across
65 files, plus production build, TypeScript, Ruff and mypy. The API receipt
contains the two new country reserve flows and two existing payout flows. Scanner
and dispatch are explicit doubles in those API tests. The 401-movement export
unit case verifies complete individual records beyond a single Excel cell limit.

All three hosted browser cases passed in 1.7 minutes on the same application
source, using the real scanner, broker and worker. Both country cases reuse a
reviewed processor source, calculate and independently approve reserves in UI,
download and inspect XLSX, then withdraw the GL source review and verify staleness
without changing saved financial rows. Source preparation/reviews use APIs. The
new upload-controls widget is covered by frontend tests; no hosted screenshot of
that upload form is claimed here.

The original artifact digest and four individually inspected result images are
retained in [the browser receipt](../phase-12/merchant-reserve-browser-9ba08d4.json):

- [UAE reviewed reserve result](screenshots/browser-workflows/AE-reserve-reviewed-ledger-9ba08d4.png)
- [UAE withdrawn ledger source](screenshots/browser-workflows/AE-reserve-ledger-withdrawn-stale-9ba08d4.png)
- [India reviewed reserve result](screenshots/browser-workflows/IN-reserve-reviewed-ledger-9ba08d4.png)
- [India withdrawn ledger source](screenshots/browser-workflows/IN-reserve-ledger-withdrawn-stale-9ba08d4.png)

These images show 100 opening, separate holds of 50 and releases of 5, closing 145,
the position/GL/batch rows and disabled stale approval. Individual dated movement
details are retained in the body and export, but collapsed provenance is not
visual evidence of those details. Five hosted CI jobs passed on this source;
the complete backend regression also passed: 4,104 passed, nine skipped, 86.27%
overall and 89.35% core coverage. Exact original JUnit and coverage are retained in
`docs/phase-12/9ba08d4-hosted-verification.json` with the verified artifact digest.
The nine skipped cases include live vendor access and separate infrastructure or
platform checks; this does not qualify real providers or clients. Later service
calendar changes need their own full hosted proof.
