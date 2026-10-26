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

`synthetic-examples/` contains generated test examples only. These are separate
from client pilots and do not establish real client or statutory qualification.
