# API verification

276 operations discovered; 414 contract/error checks; 0 currently classified failures.

Authentication/error envelope probes; valid business mutations additionally exercised by workflows. Not every parameter combination tested.

The public /system/version endpoint was initially misclassified as protected by the harness; its explicit Version response is public by design. This harness error is retained in the original run log and corrected in the rerun.

API mutations and persisted financial consistency are asserted by baseline XML and QA workflow tests; API execution receipts for population are in api-execution.jsonl.
