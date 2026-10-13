import pandas as pd, joblib, json
from sklearn.ensemble import RandomForestClassifier

X_train, X_test, y_train, y_test = joblib.load("data/processed/split_original.pkl")
X_train_res, y_train_res = joblib.load("data/processed/train_resampled.pkl")
sector_list = joblib.load("models/sector_list.pkl")
sector8_code = sector_list.index("44")

rf16 = RandomForestClassifier(n_estimators=300, max_depth=16, min_samples_leaf=50,
                               max_features=None, n_jobs=-1, random_state=42)
rf16.fit(X_train_res, y_train_res)

row = pd.DataFrame([{"Term": 24, "NoEmp": 5, "GrAppv": 50000.0, "NewExist": 2.0, "NAICS_Sector": sector8_code}])

print("Probability vs Term, depth=16/leaf=50 (same profile as before):")
for t in [6, 12, 24, 36, 60, 84, 120, 180, 240, 300, 360]:
    r = row.copy(); r["Term"] = t
    print(f"  Term={t:4d} -> raw prob={rf16.predict_proba(r)[0,1]:.4f}")

iso_old = joblib.load("models/isotonic_calibrator.pkl")
raw24 = rf16.predict_proba(row)[0, 1]
print(f"\n24-month case with depth=16 model:")
print(f"  raw RF score:                      {raw24:.4f}")
print(f"  old calibrator (fitted on depth=24): {iso_old.predict([raw24])[0]:.4f}")
print(f"  real-world actual rate for this profile: ~0.593")