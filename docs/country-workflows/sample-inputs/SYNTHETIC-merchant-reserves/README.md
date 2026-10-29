# Synthetic reserve continuity examples

These authored examples exercise mechanics, not real client or legal qualification.
`controls.json` retains the original file hashes, table types, expected row counts,
independent-control field shapes and authored expected values. The two country
populations use AED and INR respectively with explicitly assessed synthetic tax
labels, not statutory rates. The processor CSV is compatible with the existing
merchant settlement workflow; it can be reused after independent source review.

Upload all four sources, entering the separately checked controls. Review each
source independently, then select `merchant-reserve-rollforward`, June 1–30 2026
and the declared currency. Opening 100 plus two holds of 30 and 20 minus a release
of 5 gives 145. The opening GL control is May 31; the closing control is June 30.
The intermediate available balances are 130, 150 and 145. The declared sequence
orders original statement entries within a date; it is not a guessed CSV order.

The example values were authored alongside synthetic tests. They are not supplied
or independently approved client expectations. Save actual redacted pilots and
independently checked client results under `pilot-data/`, separately from these
public repository fixtures.
