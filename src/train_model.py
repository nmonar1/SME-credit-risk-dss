import json
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OneHotEncoder, FunctionTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (roc_auc_score, average_precision_score, precision_score,
                             recall_score, f1_score, confusion_matrix, classification_report)

X_train, X_test, y_train, y_test = joblib.load("data/processed/split_original.pkl")
X_train_res, y_train_res = joblib.load("data/processed/train_resampled.pkl")
print("Balanced training set:", X_train_res.shape, "| Real test set:", X_test.shape)


def evaluate(name, model):
    p = model.predict_proba(X_test)[:, 1]
    pred = (p >= 0.5).astype(int)
    print(f"\n===== {name} (on the untouched test set) =====")
    print(classification_report(y_test, pred, target_names=["Paid in full", "Defaulted"], digits=3))
    print("Confusion matrix (rows = actual, columns = predicted):")
    print(confusion_matrix(y_test, pred))
    return {
        "Model": name,
        "ROC-AUC": round(roc_auc_score(y_test, p), 4),
        "PR-AUC": round(average_precision_score(y_test, p), 4),
        "Precision": round(precision_score(y_test, pred), 4),
        "Recall": round(recall_score(y_test, pred), 4),
        "F1": round(f1_score(y_test, pred), 4),
    }


# ---------- Baseline: Logistic Regression ----------
numeric_cols = ["NoEmp", "GrAppv"]
preprocess = ColumnTransformer(
    transformers=[
        ("numeric", Pipeline([("log", FunctionTransformer(np.log1p)),
                              ("scale", StandardScaler())]), numeric_cols),
        ("sector", OneHotEncoder(categories=[list(range(24))], handle_unknown="ignore"), ["NAICS_Sector"]),
    ],
    remainder="passthrough",   # NewExist goes through unchanged
)
lr = Pipeline([("preprocess", preprocess), ("model", LogisticRegression(max_iter=1000))])
lr.fit(X_train_res, y_train_res)
lr_results = evaluate("Logistic Regression", lr)

# ---------- Main model: Random Forest ----------
with open("models/best_rf_params.json") as f:
    best = json.load(f)
print("\nRandom Forest settings from tuning:", best)
rf = RandomForestClassifier(n_estimators=300, max_features=None, n_jobs=-1, random_state=42, **best)
rf.fit(X_train_res, y_train_res)
rf_results = evaluate("Random Forest", rf)

print("\nRandom Forest feature importance:")
for name, imp in sorted(zip(X_train.columns, rf.feature_importances_), key=lambda x: -x[1]):
    print(f"  {name:14s} {imp:.3f}")

# ---------- Save ----------
results = pd.DataFrame([lr_results, rf_results])
print("\n", results.to_string(index=False))
results.to_csv("models/model_results.csv", index=False)
joblib.dump(lr, "models/logistic_regression_model.pkl")
joblib.dump(rf, "models/random_forest_model.pkl", compress=3)
print("\nSaved models and results.")