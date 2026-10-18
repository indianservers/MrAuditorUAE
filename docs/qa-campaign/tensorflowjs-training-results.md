# TensorFlow.js training and inference

Four real TensorFlow.js families were fitted: autoencoder, journal classifier, risk ranking and account classifier. The registry workflow exercised private artifact saving/loading, held-out evaluation, approval, inference, permissions and feedback. New family candidates were not approved or deployed. No metrics were invented.

On the small held-out fixture, journal and risk classifiers had F1=0; autoencoder F1 was 0.888889; account-classifier accuracy was 0.6. Exact precision/recall, OOD metrics, rankings and resource measurements are in ml-evaluation-summary.json. All four candidates are production_validated=false. Scores do not establish representative audit accuracy.

model-results.json records actual persisted model metrics, including reload checks. Small classifier training fixtures are engineering checks and must not be promoted on the basis of these scores. Broader anomaly-family precision/recall/F1/P@K and representative drift/rollback validation remain incomplete.

ML engine unit tests and build evidence: ml-tests.txt, ml-build.txt.
