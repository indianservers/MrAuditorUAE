# UAE and India pilot evidence

Save redacted client inputs in `UAE/redacted-inputs/` or `India/redacted-inputs/`.
Save independently checked expected results in the matching country's
`independent-expected-results/` folder, and reviewer decisions and supporting
checks in `review-records/`. Each country has a `pilot-manifest.template.json`
to describe the engagement, files, expected results and reviewer.

These folders are ready for supplied pilot evidence. They do not currently
contain real client files or independently approved client results. Their
contents are ignored by Git to keep client material out of repository pushes.
Do not store passwords or access tokens in manifests.

For each pilot, copy the country's manifest template and populate it only from
the supplied files and an independently checked result. Leave its awaiting-data
and not-reviewed status in place until those records actually exist. Creating
these folders or saving synthetic examples does not complete a client pilot.

`synthetic-examples/` contains generated test examples only. These are separate
from client pilots and do not establish real client or statutory qualification.

## Local evidence comparison

`scripts/validate_country_pilot.py` reads supplied evidence without executing
software, uploading files or changing a review status. Use the backend Python
environment so the current workflow catalogue is available. For example, from
the repository root:

```powershell
& backend/.venv/Scripts/python.exe scripts/validate_country_pilot.py pilot-data/UAE/review-records/your-manifest.json --country-root pilot-data/UAE
```

Use `pilot-data/India` for an India pilot. The country is declared explicitly in
the manifest; the tool checks that the selected workflow supports that country.
Shared workflows remain available in both countries.

1. Copy the manifest and review templates into the selected country's
   `review-records/` folder. Keep actual inputs in `redacted-inputs/` and
   independently prepared expected JSON in `independent-expected-results/`.
   Save a separate exported actual JSON file in `review-records/`. Compare the
   same agreed result structure; preserve the original software export and
   document any projection separately. Do not generate expectations from the
   actual result.
2. Record relative paths from the country root, using `/`, plus lowercase SHA-256
   hashes of each original input, expected result, actual result and review
   record. Every declared input needs a hash; files outside their designated
   folders and linked result roles are rejected. Each file is bounded to 8 MiB
   and the complete read population to 100 MiB, with at most 100 input files.
3. Record the actual client reference, country, workflow, period and authorized
   use reference. Expected preparer, actual-output preparer and independent
   reviewer must be distinct declared identities. Set `expected_basis` to
   `INDEPENDENT_EXTERNAL_CALCULATION` only when that basis is true.
4. In the retained review record, bind the same country, workflow, client, period,
   input hashes, expected/actual hashes and reviewer. Record the real review
   date, scope assessment and `COMPARISON_AUTHORIZED` decision. Then record its
   hash in the manifest. Set manifest `dataset_kind` to `REAL_CLIENT_PILOT`,
   `review_status` to `INDEPENDENT_REVIEW_RECORDED` and `status` to
   `READY_FOR_LOCAL_COMPARISON` only after these records actually exist.

Exit code 0 means retained hashes and scope agree and the two parsed JSON results
match; 1 means a result mismatch; 2 means missing or invalid evidence. Duplicate
JSON keys, non-finite numbers and excessive nesting fail closed. Object key order
is irrelevant; array order, null versus zero, booleans, numeric strings and
missing keys remain distinct. JSON numbers use exact decimal equality, with no
tolerance or rounding. Two separate independently prepared files may legitimately
have identical bytes. A shared hard link cannot serve both result roles.

The JSON output identifies the manifest and validator hashes but omits client
identities, source paths and result contents. It makes no legal/production or
professional-qualification claim. Consent, real-client origin, preparer identity,
independence, document meaning and completeness still need human verification.
A valid template is deliberately insufficient. Synthetic temporary-file tests
exercise the validator; they do not populate these client folders.
