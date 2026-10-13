import json
import joblib
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

X_train, X_test, y_train, y_test = joblib.load("data/processed/split_original.pkl")
X_train_res, y_train_res = joblib.load("data/processed/train_resampled.pkl")

# Carve a calibration slice from the ORIGINAL (real-distribution) training data.
# This must be data the model has never been trained on directly, and it must
# keep the real ~20% default rate -- that's the whole point of calibration.
X_tr2, X_cal, y_tr2, y_cal = train_test_split(
    X_train, y_train, test_size=0.15, random_state=7, stratify=y_train
)
print("Calibration slice:", X_cal.shape, "| default share:", round(y_cal.mean(), 3))

with open("models/best_rf_params.json") as f:
    best = json.load(f)
print("Using RF settings:", best)

rf = RandomForestClassifier(n_estimators=300, max_features=None, n_jobs=-1, random_state=42, **best)
rf.fit(X_train_res, y_train_res)

p_raw_test = rf.predict_proba(X_test)[:, 1]
p_raw_cal = rf.predict_proba(X_cal)[:, 1]


iso = IsotonicRegression(out_of_bounds="clip")
iso.fit(p_raw_cal, y_cal)
p_cal_test = iso.predict(p_raw_test)

print("\nMean predicted default prob on real test set (actual rate ~0.203):")
print("  raw model:       ", round(p_raw_test.mean(), 3))
print("  calibrated model:", round(p_cal_test.mean(), 3))

print("\nBrier score (lower = more honest probabilities):")
print("  raw:       ", round(brier_score_loss(y_test, p_raw_test), 4))
print("  calibrated:", round(brier_score_loss(y_test, p_cal_test), 4))

print("\nROC-AUC (should barely move -- calibration doesn't change ranking, only scale):")
print("  raw:       ", round(roc_auc_score(y_test, p_raw_test), 4))
print("  calibrated:", round(roc_auc_score(y_test, p_cal_test), 4))


low_cut = np.percentile(p_cal_test, 80)
high_cut = np.percentile(p_cal_test, 98)

labels = {"low_max": round(float(low_cut), 4), "high_min": round(float(high_cut), 4),
          "bucket_names": ["Low", "Moderate", "Elevated"]}
with open("models/risk_thresholds.json", "w") as f:
    json.dump(labels, f)

for lo, hi, label in [(0, low_cut, "Low"), (low_cut, high_cut, "Moderate"), (high_cut, 1.01, "Elevated")]:
    mask = (p_cal_test >= lo) & (p_cal_test < hi)
    print(f"{label:9s} n={mask.sum():6d} ({mask.mean()*100:.1f}%)  actual default rate={y_test[mask].mean():.3f}")
print("\nSaved:", labels)

joblib.dump(iso, "models/isotonic_calibrator.pkl")