# TensorFlow.js monitoring integration

Optional monitoring inference uses the current deployed same-engagement Phase 9 model family and actual Node/TensorFlow.js CPU inference. It retains model/deployment IDs, feature schema, calibration, input snapshot, raw score, drift, experimental status and reviewer state. Financial arithmetic remains Decimal; floating point is confined to ML features/scores. Classification suggestions are not fraud findings.

The bounded scored slice is registered as a private immutable dataset with unknown labels and test-only splits, then linked to a standard ML inference event. Existing evidence-backed feedback and independent curation can consume that event; original test split assignments are preserved, with no automatic retraining or deployment. Models remain experimental and validated only on the Phase 9 controlled synthetic task. Real-world fraud detection accuracy and calibrated probabilities are not claimed.
