# Bugs Found And Fixed

Integration testing corrected the IFRS source profit key to totals.profit. Current-law research replaced obsolete active MD88 with MD96. Tax rounding residuals now attach to positive-income allocations. Deployment history is selected per model family. Gzip versioned private storage resolves large dataset object limits with bounded decompression. Browser testing found progress/cancellation waiting on engagement locks; these now use nonlocking permission checks. Windows preview locks required stopping the verified preview before building. Three npm transitive moderate advisories remain unpatched and documented.

A repeated explicit training request now has a distinct request key, while callers may supply a stable key for retry idempotency. Browser tests verify both completion and actual active-child cancellation. Tax KPI display formats exact backend decimal strings for readability; raw values remain available in the drill-down.
