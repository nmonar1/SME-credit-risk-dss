import os
import joblib
import pandas as pd
from sklearn.model_selection import train_test_split
from imblearn.over_sampling import SMOTENC

os.makedirs("models", exist_ok=True)

df = pd.read_csv("data/processed/cleaned_data.csv", dtype={"NAICS_Sector": str}, low_memory=False)
df["ApprovalFY"] = pd.to_numeric(df["ApprovalFY"], errors="coerce")
print("Loaded:", df.shape)

before = len(df)
df = df[df["NAICS_Sector"] != "Unknown"]
print("Excluded unknown-sector rows:", before - len(df), "| remaining:", len(df))
print("Default counts:")
print(df["Default"].value_counts())

FEATURES = ["NoEmp", "GrAppv", "NewExist", "NAICS_Sector"]
X = df[FEATURES].copy()
y = df["Default"]
print("Features:", list(X.columns))

sector_list = sorted(X["NAICS_Sector"].unique())
print("Number of sectors:", len(sector_list))
print(sector_list)
X["NAICS_Sector"] = pd.Categorical(X["NAICS_Sector"], categories=sector_list).codes.astype(int)

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
print("Train:", X_train.shape, "Test:", X_test.shape)
print("Train default share:", round(y_train.mean(), 3), "| Test default share:", round(y_test.mean(), 3))

cat_idx = [FEATURES.index("NewExist"), FEATURES.index("NAICS_Sector")]
smote = SMOTENC(categorical_features=cat_idx, random_state=42)
X_train_res, y_train_res = smote.fit_resample(X_train, y_train)
X_train_res = X_train_res.astype(X_train.dtypes.to_dict())
print("Train after SMOTENC:", X_train_res.shape)
print(y_train_res.value_counts())
print("Sector codes range:", X_train_res["NAICS_Sector"].min(), "to", X_train_res["NAICS_Sector"].max())
print("NewExist values:", sorted(X_train_res["NewExist"].unique()))
print("Missing values:", int(X_train_res.isnull().sum().sum()))

joblib.dump(FEATURES, "models/feature_columns.pkl")
joblib.dump(sector_list, "models/sector_list.pkl")
joblib.dump((X_train, X_test, y_train, y_test), "data/processed/split_original.pkl")
joblib.dump((X_train_res, y_train_res), "data/processed/train_resampled.pkl")
joblib.dump(df["ApprovalFY"], "data/processed/approval_fy.pkl")
print("Saved.")