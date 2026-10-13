import pandas as pd

df = pd.read_csv("data/raw/SBAnational.csv", low_memory=False)
print("Loaded:", df.shape)

df = df[df["MIS_Status"].notna()]
print("After dropping missing target:", df.shape)

currency_cols = ["DisbursementGross", "BalanceGross", "ChgOffPrinGr", "GrAppv", "SBA_Appv"]

for col in currency_cols:
    df[col] = (
        df[col]
        .astype(str)
        .str.replace(r"[$,]", "", regex=True)
        .str.strip()
        .astype(float)
    )

print("Currency columns cleaned. Sample:")
print(df[currency_cols].head(3))

def clean_flag(series):
    series = series.astype(str).str.strip()
    return series.apply(lambda x: x if x in ["Y", "N"] else "Unknown")

df["RevLineCr"] = clean_flag(df["RevLineCr"])
df["LowDoc"] = clean_flag(df["LowDoc"])

print("RevLineCr after cleaning:")
print(df["RevLineCr"].value_counts())
print("LowDoc after cleaning:")
print(df["LowDoc"].value_counts())

df["NewExist"] = df["NewExist"].apply(lambda x: x if x in [1.0, 2.0] else None)
df = df[df["NewExist"].notna()]
print("After fixing NewExist:", df.shape)

df["NAICS_Sector"] = df["NAICS"].astype(str).str[:2]
df["NAICS_Sector"] = df["NAICS_Sector"].replace("0", "Unknown")

print("NAICS_Sector value counts:")
print(df["NAICS_Sector"].value_counts().head(10))

df["Default"] = df["MIS_Status"].map({"P I F": 0, "CHGOFF": 1})

print("Default value counts:")
print(df["Default"].value_counts())

leak_or_id_cols = ["ChgOffDate", "ChgOffPrinGr", "LoanNr_ChkDgt", "Name",
                    "City", "Bank", "BankState", "Zip", "ApprovalDate", "DisbursementDate",
                    "MIS_Status", "BalanceGross"]
df = df.drop(columns=leak_or_id_cols)

print("Final shape after dropping leakage/ID columns:", df.shape)
print("Remaining columns:", list(df.columns))

df.to_csv("data/processed/cleaned_data.csv", index=False)
print("Saved cleaned data to data/processed/cleaned_data.csv")

