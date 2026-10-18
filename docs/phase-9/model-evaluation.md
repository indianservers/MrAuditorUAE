# Model Evaluation

Actual completed runs supply precision, recall, F1, false-positive rate, confusion matrices, threshold sweeps/PR points, budget ranking and Brier scores. Account evaluation includes per-class results and simple baselines. Test and OOD cohorts are separate. No representative authorized real-client evaluation was supplied. See model-summary.json and training-results.json for exact architectures, epochs, losses, hyperparameters and baseline comparisons. Do not interpret perfect simple synthetic classifier results as real audit effectiveness.

The actual existing Phase 2 AnalyticsEngine was also evaluated without labels as inputs. Any-rule review flags on 2,400 held-out fixture lines produced F1 0.264819; see existing-rule-comparison.json. This is a broad review-signal baseline against narrow injected labels, not a real-world audit-quality comparison.
