# Merchant gross-to-net bank settlement

`merchant-settlement-bridge` compares independently retained book activity,
processor settlement batches and explicit bank allocations. It is available for
UAE and India engagements. It addresses merchant-acquirer and payment-gateway
settlements without treating a net receipt as gross revenue or a tax conclusion.

Prepare and independently review four source versions in the existing source
screen, then select them in the calculation screen:

- **books / merchant-activity:** Positive original sale, refund and chargeback records attributed to an explicit merchant, processor, batch and currency.
- **processor / merchant-settlements:** One original reported batch with its activity period, settlement date, components, reported net and assessed tax classification.
- **bank / transactions:** Independent signed bank movements, credit-positive, for the declared account and currency.
- **allocations / merchant-bank-allocations:** Exact processor-row and bank-row links with signed amounts and supporting assessments.

The calculation requires an explicit reporting window within the engagement,
account and currency. It uses exact monetary and date controls; it does not use
fuzzy matching or tolerances. Each source retains the normal uploaded-file hash,
row count and currency-total controls. Processor sources additionally require
independently declared totals for **every** component, including assessed zeros:
`sales`, `refunds`, `chargebacks`, `fees`, `fee_tax`, `withholding`, `reserve_held`,
`reserve_released` and `amount`. Missing values are not zero. Declare these controls
from independently checked schedules; summing the imported file itself is not
independent verification.

The bridge checks:

```
sales - refunds - chargebacks - fees - fee tax - withholding
      - reserve held + reserve released = reported net settlement
reported net settlement = explicitly allocated signed bank movements
```

Book sales, refunds and chargebacks are compared separately to the processor's
reported amounts. A correct net cannot hide equal inflation of gross sales and
refunds. Original activity references must be unique within merchant, processor,
batch, currency and kind; use a genuine line-level reference where orders contain
multiple records. Competing batches, unknown allocations, duplicated allocation
pairs, excessive allocation and inconsistent direction are rejected. Book activity
must fall within its batch period. Bank movements cannot predate the declared
processor settlement and must be within the selected review window.

One batch may settle through multiple bank movements, and multiple batches may
share a bank movement through explicit nonduplicated allocations. Negative net
settlements can link only to negative bank movements. Every bank remainder is a
separate exception, and a net or component difference blocks approval. Committed
book-ledger sources cannot stand in for independent bank evidence.

UAE processor rows require `tax_country: AE` and an assessed `UAE_VAT`,
`FOREIGN_TAX` or `NO_TAX_ASSESSED` fee-tax classification. India uses
`tax_country: IN` and `INDIA_GST`, `FOREIGN_TAX` or `NO_TAX_ASSESSED`.
`NO_TAX_ASSESSED` cannot carry nonzero fee tax. Classification and monetary
components require retained source references and meaningful assessment. These
are reported facts, not calculated statutory rates, recovery eligibility or
withholding-credit entitlement. The workflow does not assume that a processor's
reported tax treatment is legally correct.

Results preserve original book and allocation IDs, component amounts,
book-component differences, calculated net, arithmetic variance, bank allocations
and bank residuals. The existing review separation, history, working-paper and
export controls apply. Source replacement or withdrawal makes dependent results
stale while retaining the original result body.

Synthetic UAE/AED and India/INR files with hashes and an independently stated
arithmetic example are in
`sample-inputs/SYNTHETIC-merchant-settlements/`. They are not real client files or
professionally qualified expected schedules. The separate India MSE timing and
UAE native-bank browser checks remain separate capabilities.

This procedure does not authenticate banks or processors, reserve cash across
other workflows, post journals, execute payments, prove complete sales populations,
roll forward reserve liabilities, calculate FX or qualify tax/filing obligations.
Unrepresented processor components require a separately assessed supported
procedure; do not silently fold them into fees or net them away.
