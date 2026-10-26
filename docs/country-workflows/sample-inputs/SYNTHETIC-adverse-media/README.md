# Synthetic adverse-media review examples

These ten fictional datasets exercise UAE first and India second. They contain no
real person, provider query, independently authenticated identity or media finding.
Expected outcomes are engineering fixtures, not professional client conclusions.

Each country has a different-subject collision, a completed search with no mentions,
a same-subject observation, unresolved identity and unavailable-search example.
Unavailable search results remain incomplete even when the mention CSV is empty.
Reported allegations are never treated as established legal facts. No set issues
clearance or automatically rejects a subject. Follow-up dates do not enable a
scheduled monitor.

Upload the original TXT files as retained evidence first. Replace every fictional
UUID listed in `document_version_placeholders` with the returned **file-version ID**,
including the identity-support reference in the mention row. Parent evidence-record
IDs are different. Preserve the original file bytes and SHA-256 values. The files
describe fictional observations only; they are not suitable as real query or identity
evidence. The `.invalid` URLs deliberately resolve to no real article.

Import `subjects.csv`, `searches.csv`, `mentions.csv` and `policy.csv` using each
manifest's table type, expected row count, empty monetary controls and nil reason
where specified. Media sources use counts, not currency totals. Independently review
all four sources, then select `adverse-media-review` at the declared review date.
Final approval is separate from source review; same-subject observations require
documented exception disposition. Hard evidence gaps cannot be overridden.

The policy country is the engagement review context. A subject's country records its
domicile and may differ, including foreign vendors or implementing partners. Policy
scope and query-age limits are supplied assessments, not statutory country defaults.
Published hashes cover exact LF CSV/TXT bytes; version IDs require replacement
after upload. Real client validation belongs separately in `pilot-data/`.
