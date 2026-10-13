"""Finds one Low, one Moderate and one Elevated example for the demo buttons, using YOUR saved model.
Run from the project root:  python src/find_presets.py

How examples are chosen (so you can describe it in your report):
  - only familiar sectors are used, so the demo reads like a real branch's applications
  - Low and Moderate: the score closest to the middle of the band, never a degenerate 0.000
  - Elevated: the highest score, which keeps it safely inside the band
  - ties are broken in favour of an ordinary-looking profile (about $75k, about 8 employees, established)
  - every example must sit at least 0.03 inside its band, so a small tweak in a live demo cannot flip the band
"""
import json
import math
import itertools
import joblib
import pandas as pd

from labels import NAICS_LABELS

DEMO_SECTORS = ["23", "42", "44", "45", "48", "53", "54", "62", "72", "81"]
MIN_MARGIN = 0.03

rf = joblib.load("models/random_forest_model.pkl")
iso = joblib.load("models/isotonic_calibrator.pkl")
sector_list = joblib.load("models/sector_list.pkl")
FEATURES = joblib.load("models/feature_columns.pkl")
with open("models/risk_thresholds.json") as f:
    TH = json.load(f)

amounts = [5000, 10000, 15000, 20000, 25000, 35000, 50000, 75000, 100000, 150000, 250000, 500000]
employees = [0, 1, 2, 3, 5, 8, 12, 20, 40]
ages = [1, 6]            # 1 = new business, 6 = established
grid = pd.DataFrame(list(itertools.product(sector_list, amounts, employees, ages)),
                    columns=["sector", "amount", "emp", "age"])

X = pd.DataFrame({
    "NoEmp": grid["emp"], "GrAppv": grid["amount"].astype(float),
    "NewExist": grid["age"].apply(lambda a: 2.0 if a <= 2 else 1.0),
    "NAICS_Sector": grid["sector"].apply(sector_list.index),
})[FEATURES]
grid["score"] = iso.predict(rf.predict_proba(X)[:, 1])
grid["band"] = grid["score"].apply(lambda p: "Low" if p < TH["low_max"] else ("Moderate" if p < TH["high_min"] else "Elevated"))
grid["margin"] = grid.apply(lambda r: TH["low_max"] - r["score"] if r["band"] == "Low"
                            else (min(r["score"] - TH["low_max"], TH["high_min"] - r["score"]) if r["band"] == "Moderate"
                                  else r["score"] - TH["high_min"]), axis=1)
grid["plaus"] = grid.apply(lambda r: abs(math.log(r["amount"] / 75000)) + 0.5 * abs(math.log((r["emp"] + 1) / 9))
                           + (0.0 if r["age"] == 6 else 0.3), axis=1)

TARGET = {"Low": TH["low_max"] / 2, "Moderate": (TH["low_max"] + TH["high_min"]) / 2, "Elevated": None}

print(f"Searched {len(grid):,} realistic applications. Band counts: {grid['band'].value_counts().to_dict()}\n")
presets = {}
for band in ["Low", "Moderate", "Elevated"]:
    pool = grid[(grid["band"] == band) & (grid["margin"] >= MIN_MARGIN)]
    demo_pool = pool[pool["sector"].isin(DEMO_SECTORS)]
    if demo_pool.empty:
        print(f"({band}: no example in the familiar sectors, searching all sectors)")
        demo_pool = pool
    if demo_pool.empty:
        print(f"{band}: NO example found with margin >= {MIN_MARGIN}.\n")
        continue
    demo_pool = demo_pool.copy()
    if TARGET[band] is None:
        demo_pool["gap"] = -demo_pool["margin"].round(2)          # biggest margin first
    else:
        demo_pool["gap"] = (demo_pool["score"] - TARGET[band]).abs().round(2)
    ranked = demo_pool.sort_values(["gap", "plaus"])
    print(f"{band} - top 3 candidates (target score: {'highest' if TARGET[band] is None else round(TARGET[band], 3)}):")
    for _, r in ranked.head(3).iterrows():
        print(f"   {NAICS_LABELS[r['sector']]:<40} ${r['amount']:>9,.0f}  emp={int(r['emp']):>2}  age={int(r['age'])}  score={r['score']:.3f}  margin={r['margin']:.3f}")
    print()
    best = ranked.iloc[0]
    presets[band] = {"business_name": f"Demo {band} Risk Co", "sector": best["sector"], "num_employees": int(best["emp"]),
                     "business_age": int(best["age"]), "loan_amount": float(best["amount"]), "loan_term": 60}

with open("models/demo_presets.json", "w") as f:
    json.dump(presets, f, indent=2)
print("Saved models/demo_presets.json with:", list(presets))