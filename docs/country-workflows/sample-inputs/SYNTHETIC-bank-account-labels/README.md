# Synthetic single-account statement labels

These fictional UAE/AED and India/INR CSVs preserve the original text identifier
`00000123`. They are not bank-issued statements or proof of account ownership.

Upload `statement.csv` as retained evidence, prepare a bank supporting table with
GL account label `100` and a meaningful mapping assessment, then obtain independent
source review. The mapping changes the matching label while retaining the original
account identifier in each row. `expected.json` records the original file hash and
literal expected mapping, not an independently checked client result.

For the matching test, use one controlled journal with a debit of 1 to GL 100,
a credit of 1 to an offset account, reference SYN-SHARED and date 1 June 2026.
Choose AED for the UAE GL import and INR for India. Select GL 100 alone.
A matching proposal still requires recorded preparer acceptance and independent
approval. A source without a declared account, a different GL label or mixed
original accounts must not be used as one bank matching scope.

Closing-balance equations, foreign-currency transaction books and separately
reviewed account-ownership evidence use the existing country Bank balance
reconciliation workflow. This source label alone does not establish those controls.

Git preserves these CSVs as literal byte fixtures so Windows checkout line-ending
conversion cannot invalidate their saved hashes. Both staged blobs were checked
against their expected hashes.
