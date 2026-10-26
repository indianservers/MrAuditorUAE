# Synthetic explicit expense cut-off schedules

These fictional UAE and India examples exercise shared accounting arithmetic.
They do not establish client validation or legal/tax recognition. The example
period starts reflect the disposable engagements; always use the actual
engagement reporting period. No country-specific tax rates are inferred.

Upload each CSV as separate retained evidence. Prepare it using the table type,
independent row count and currency totals in `scope-controls.json`. Review all
three sources independently, select `expense-cutoff`, select documents plus the
optional recognition and posting roles, and use the manifest reporting and
review dates. Select both optional roles for explicit schedules. If no ledger
postings were observed, prepare an explicitly reviewed nil posting source;
leaving the source absent does not establish a nil population.

`split-reversal` allocates an invoice of 1,200 into a current-period amount of
100 and an assessed future amount of 1,100. Three expense-account postings
(80, 40 and -20) agree to current expense of 100. All posting IDs, accounts,
references and dates remain available in the posting table and XLSX.

`late-credit` allocates a credit note of -1,200. The current credit of -100
was posted on 10 July, after the 30 June reporting date. Current posted expense
is zero and the period difference is 100; subsequent credit is separately
shown as -100. Independent exception disposition and approval are required.

Allocations must total the document amount exactly, regardless of money
tolerance. Recognition and posting dates on an explicit-schedule document must
stay blank; dates belong to the linked schedules. Future allocations are
assessed schedules, not assertions of completed services. Supplied postings
cover expense recognition only: prepaid-asset, payable, tax and cash controls
need their own reconciliations. The sources do not prove population completeness,
ledger authenticity, legal recognition, or an audit opinion.
