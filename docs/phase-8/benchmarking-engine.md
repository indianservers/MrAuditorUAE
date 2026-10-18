# Benchmarking Engine

Authorized CSV/XLSX imports accept up to 50,000 observations and 10 MiB per immutable dataset version. Expanded workbooks are capped at 30 MiB. Formula cells, duplicate company/year rows, non-finite numbers and empty datasets fail. Source versions, license references, expiry, permitted derived/raw exports and AI disclosure rights are explicit.

Screening records support batches of 200 decisions with independent, functional, loss and extraordinary-event reviews. Pending decisions prevent ready status. Conflicting decisions and duplicate company/year observations across sources require resolution. Missing metrics and zero denominators fail unless explicit exclusion is approved. Mixed currencies require a separately reviewed conversion dataset.

Statistics include n, missing count, minimum, maximum, mean, median, Q1 and Q3. Inclusive interpolation uses (n−1)p; exclusive interpolation uses (n+1)p−1 and returns undefined outside supported sample ranks. Year-specific, company-unweighted and financial-amount-weighted pooling are distinct. Weighted pooling rejects PLI-point adjustments rather than silently ignoring them. No median adjustment is automatic.

The persisted demo has 5,000 accepted observations in its largest study. They are named SYNTHETIC and cannot support a real market conclusion. Commercial sources are user imports subject to licensing; no vendor API, scraper, invented comparable or production license is supplied.
