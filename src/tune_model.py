import json
import time
import joblib
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, average_precision_score
from imblearn.over_sampling import SMOTENC

X_train, X_test, y_train, y_test = joblib.load("data/processed/split_original.pkl")

# Validation set carved from the ORIGINAL training data (real class distribution)
X_tr, X_val, y_tr, y_val = train_test_split(
    X_train, y_train, test_size=0.2, random_state=42, stratify=y_train
)
print("Inner train:", X_tr.shape, "| Validation:", X_val.shape)
print("Default share - inner train:", round(y_tr.mean(), 3), "| validation:", round(y_val.mean(), 3))

# Balance ONLY the inner training part
cat_idx = [list(X_tr.columns).index("NewExist"), list(X_tr.columns).index("NAICS_Sector")]
X_tr_res, y_tr_res = SMOTENC(categorical_features=cat_idx, random_state=42).fit_resample(X_tr, y_tr)
X_tr_res = X_tr_res.astype(X_tr.dtypes.to_dict())
print("Inner train after SMOTENC:", X_tr_res.shape)

results = []
for depth in [12, 16, 24]:
    for leaf in [20, 50]:
        start = time.time()
        rf = RandomForestClassifier(
            n_estimators=100, max_depth=depth, min_samples_leaf=leaf,
            max_features=None, n_jobs=-1, random_state=42,
        )
        rf.fit(X_tr_res, y_tr_res)
        p = rf.predict_proba(X_val)[:, 1]
        roc = roc_auc_score(y_val, p)
        pr = average_precision_score(y_val, p)
        print(f"max_depth={depth:>2} min_samples_leaf={leaf:>2} | ROC-AUC {roc:.4f} | PR-AUC {pr:.4f} | {time.time() - start:.0f}s")
        results.append({"max_depth": depth, "min_samples_leaf": leaf, "roc_auc": roc, "pr_auc": pr})

best = max(results, key=lambda r: r["pr_auc"])
print("\nBEST SETTINGS:", best)

with open("models/best_rf_params.json", "w") as f:
    json.dump({"max_depth": best["max_depth"], "min_samples_leaf": best["min_samples_leaf"]}, f)
pd.DataFrame(results).to_csv("models/tuning_results.csv", index=False)
print("Saved models/best_rf_params.json and models/tuning_results.csv")