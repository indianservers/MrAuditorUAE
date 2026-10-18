# Backup and restore drill

Evidence date: 18 October 2026. Scope: local synthetic release candidate.

Result: PASS. Source auditos_phase7_demo -> isolated empty auditos_phase12_restore_test. Custom-format pg_dump used an exported repeatable-read snapshot; every public table's row count and sorted complete-row hash matched after pg_restore. 1205 private objects were encrypted, decrypted, extracted into a separate directory and SHA-256 matched. Database restore plus fingerprint verification: 43.130s; entire drill 69.735s. Evidence: recovery.json and recovery-log.txt.

Backup archives and key are ignored local artifacts. This is a synthetic local encryption/recovery demonstration, not a production key-custody design. Production requires separated KMS/offline recovery authority, remote immutable retention, PITR, restore into an isolated account/network, alerting and independent acceptance. recovery-app-smoke.json additionally verifies actual login, readiness, client/ledger reads and original-hash evidence download using the restored database and restored object directory; ledger rows remain unchanged. The recovery script refuses nonempty targets and never drops existing databases. Recovery point predates later browser proof records; counts are a consistent snapshot, not a claim of final demo counts.
