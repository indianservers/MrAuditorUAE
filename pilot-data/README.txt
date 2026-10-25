UAE and India pilot validation inputs

UAE/ and India/ contain redacted-inputs, independent-expected-results and review-records folders, plus a manifest template. These folders currently contain no real client files or professional approvals. Their contents are ignored by Git; the empty structure and manifest templates are saved in the repository.

synthetic-examples/ contains the existing authored engine scenarios with their literal input sources and expected behavior. Every example is labelled SYNTHETIC_ENGINE_FIXTURE and is not client data or a country legal qualification. The catalog preserves the source fixture hash and country/workflow. Additional native-format examples remain under docs/country-workflows/sample-inputs/.

For a real pilot, save authorized redacted originals in the relevant country input folder. Save independently prepared expected results separately, then record the actual input hashes, period, preparer and independent reviewer in a working copy of the manifest under review-records. Expected results must be checked independently of the software output. Record actual comparisons, unresolved cases and review conclusions without replacing original evidence.

Regenerate unchanged synthetic examples with backend/.venv/Scripts/python.exe scripts/export_country_pilot_examples.py. Existing differing case files are preserved rather than overwritten.

The current catalogue contains 154 synthetic engine fixtures (101 UAE, 53 India). Unchanged example files keep their original bytes and historical source-fixture hash when the fixture source gains cases. The catalogue records each file's original hash and the current generator source hash separately. A change to the case, its expected result or other metadata still stops regeneration for manual preservation; it is never silently overwritten. These hashes identify fixture versions, not professional validation.
