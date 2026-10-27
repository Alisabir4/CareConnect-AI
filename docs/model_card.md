# No-show model card

## Intended use

Portfolio demonstration of a lightweight prediction pipeline for optional care-team planning. It must not be used to deny, delay, price, or penalize access to care.

## Data and features

`backend/scripts/train_no_show_model.py` generates 4,000 synthetic records deterministically (seed 42). No external dataset is used, so no external dataset license applies. Features are lead time in days, appointment weekday, and appointment hour. Personal identifiers and sensitive demographic features are excluded. A stratified 75/25 split occurs before fitting a standard scaler and class-weighted logistic regression pipeline.

## Evaluation

The script saves precision, recall, F1, ROC-AUC, confusion matrix, class distribution, sklearn version, and a decision threshold of 0.55. A `DummyClassifier(strategy='prior')` baseline is evaluated beside logistic regression. Metrics are generated at train time in `backend/models/metrics.json`. Because synthetic labels are generated from a known formula, these results characterize the script's invented data process only; they do not establish real-world performance or fairness. No result is shown before a report exists. Model loading refuses a sklearn version mismatch and asks the operator to retrain in the active environment.

## Limitations

No real appointment data, external validation, subgroup analysis, calibration review, or clinical workflow evaluation is included. The API describes low risk as under 0.25, moderate as 0.25–0.54, and high as 0.55 or above. Thresholds are demonstration choices, not clinical recommendations. Missing or incompatible model artifacts produce an explicit unavailable response.
