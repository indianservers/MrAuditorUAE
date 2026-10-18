# TensorFlow.js validation

Evidence date: 18 October 2026. Scope: local synthetic release candidate.

Four existing families remain experimental: autoencoder, journal classifier, risk ranking and account classifier. The three Node engine tests pass; backend workflow tests exercise dataset/model permission, artifact hash, deployment, feedback and scope rules. Browser training/cancellation, measured curves and held-out confusion displays execute real Node jobs. Artifacts remain in the existing private versioned store, subject to storage admission. ML metadata reads no longer hold training engagement locks, and inference rechecks authorization/current deployment before persisting.

Synthetic held-out labels and earlier deterministic/statistical comparisons are software evidence, not a new independent customer-data validation. No new representative unseen real dataset was available. Calibration, generalization, bias, drift and production deployment remain experimental gates. Three moderate transitive advisories remain in npm's TFJS/argparse/sprintf-js chain; no compatible patched sprintf-js release was found by npm lookup. Do not replace TFJS with npm's suggested obsolete major version merely to clear a report. Disable ML entitlements for customer production until accepted.
