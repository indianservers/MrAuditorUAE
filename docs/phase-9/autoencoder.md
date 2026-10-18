# Autoencoder

A genuine dense 16/24/6/16 ReLU/linear autoencoder trains on 6,170 known normal fixture lines. Held-out validation normal errors calibrate the 95th percentile threshold. Inference returns raw reconstruction error, normalized error divided by error plus threshold, threshold and reconstruction components. Scores are not fraud probabilities. See the actual false-positive rate and OOD results in training-results.json.
