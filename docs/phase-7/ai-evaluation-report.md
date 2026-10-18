# Ai Evaluation Report

Executed:13 provider tests; existing source/schema/provider/private storage/grounding and independent-review tests; all20 VAT tasks through the configured diagnostic mock, one tenant budget rejection on21st call, independent acceptance without financial mutation, and real pypdf text extraction. Full case counts are in regression-test-matrix.md; task iterations are not counted as20 separate pytest cases.

The gateway rejects unsupported task names, unauthorized models/providers, unapproved external disclosure, oversized context, invalid structured output, unallowlisted evidence/legal references and stale sources. Existing AI mock/malformed/adversarial fixtures were retained and rerun. Findings about prompt injection are bounded to those fixtures; no broad jailbreak-resistance claim.

BLOCKED: external provider VAT legal accuracy, real image OCR, multilingual invoices, hallucination rates and model quality metrics. No provider credentials/model approval/labelled corpus were supplied. Mock responses are clearly diagnostic and never scored as correct expert advice. Invoice extraction in the mock returns no verified fields; separate literal text extraction remains unverified until human review.
