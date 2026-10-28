SYNTHETIC India micro/small supplier payment-timing examples

These are authored mechanics fixtures, not clients, approved legal schedules or
registry results. Reference strings are declared references, not proof that the
underlying supplier, acceptance or agreement documents were verified.

In an India engagement, import assessments.csv as msme-supplier-assessments,
invoices.csv as msme-invoices, bank.csv as transactions, and allocations.csv as
item-allocations. Each file has one data row. The currency controls are empty
for assessments, INR=100 for invoices/allocations, and INR=-100 for bank.
Retain clean original evidence and independently review each source before use.

Choose India assessed micro/small supplier invoice and bank payment timing.
Buyer: SYNTHETIC-BUYER; account: SYNTHETIC-ACCOUNT; currency: INR; first/last
invoice month: April 2026; bank window starts 1 April 2026; cutoff: 30 April 2026;
bank payment sign: debit-negative. The no-written-agreement example has assessed
delivery on 1 April, due date 16 April and full payment on that date.

For the partial-late example, replace bank.csv with bank-late.csv and
allocations.csv with allocations-partial.csv. The allocation control becomes
INR=40. This retains INR 40 paid late and INR 60 overdue/unpaid, with INR 60 of
the bank debit unallocated in this review. These amounts are not netted away.

Assessments supply explicit eligibility and effective scope; the workflow does
not infer micro/small registration or trade eligibility from invoice amounts or
supplier names. Missing acceptance, qualification or timely-objection-removal
evidence stays pending. Written dates are constrained by the assessed 45-day cap;
longer terms remain a visible review issue. Calendar counts are literal days.

The result is a payment-timing workpaper. It is not a Section 43B(h)/37(2)(g)
tax deduction, Section 16 interest calculation, Section 22 disclosure pack,
payment instruction, global cash reservation or signed professional conclusion.
Credit-note setoffs and tax-year/interest consequences require separate assessed
procedures. Save actual client files and independent results under pilot-data/.
