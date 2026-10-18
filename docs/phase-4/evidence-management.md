# Private evidence management

Evidence uses the existing opaque UUID-key private object store. Each upload creates a separate immutable file version with SHA-256, size, filename, media type, object key/version, scan status and actor. No public object URL is returned to readers. There is no evidence deletion or silent replacement endpoint.

Supported attachment formats: PDF, CSV, XLSX, DOCX, PNG and JPEG. File extensions and signatures are checked. Office archives have decompression limits and reject macros, embedded objects and external relationships. Uploads are bounded at both proxy and API layers. Files are never executed or embedded as active previews.

Configure `EVIDENCE_CLAMAV_HOST` and optional `EVIDENCE_CLAMAV_PORT` for the ClamAV INSTREAM protocol. Missing/unreachable scanning quarantines the file; a non-clean scanner result rejects it. A quarantined version cannot be downloaded or submitted for evidence approval. The clean path has a declared scanner test double in integration tests; a live ClamAV deployment was not available during verification.

Downloads re-authorize the engagement, resolve the exact file version, verify its SHA-256 and record a download event. They use attachment disposition, octet-stream and sandbox headers. The BFF retains attachment/security headers and supplies the tenant header from the authenticated client request.

Production ObjectStore requires a versioned S3 bucket, all public-access-block flags and an explicit KMS key; local storage is development-only. Live S3/KMS connectivity was not tested. Retention dates are stored, while automatic retention enforcement, legal holds, lifecycle purging and OCR/page extraction are not implemented. Evidence presence or a clean malware scan never establishes audit sufficiency or reliability.
