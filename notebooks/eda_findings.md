# EDA Findings — SBA Loan Dataset

## 1. Dataset size
- Rows: 899,164
- Columns: 27
- File: SBAnational.csv (179 MB)

## 2. Target variable: MIS_Status
- `P I F` (Paid In Full): 739,609 (82.4%)
- `CHGOFF` (Charged Off / default): 157,558 (17.6%)
- Missing: 1,997 (0.2%)
- Raw default rate: ~17.6% → clear class imbalance
- Justification for SMOTE in Phase 3

## 3. Columns with missing data
- `ChgOffDate` (736,465 missing) — structurally sparse; only exists for charged-off loans
- `RevLineCr` (4,528) — minor
- `LowDoc` (2,582) — minor
- `DisbursementDate` (2,368)
- `MIS_Status` (1,997) — must drop these rows (target)
- `BankState` (1,566), `Bank` (1,559), `NewExist` (136), `City` (30), `State` (14), `Name` (14)
- All others: complete

## 4. Columns needing cleaning before modelling
- `RevLineCr`, `LowDoc`: contain junk values (`0`, `1`, `T`, ` `, `C`, `A`, `R`, `` ` ``) — must be standardised to Y/N/Unknown
- Currency columns (`DisbursementGross`, `BalanceGross`, `ChgOffPrinGr`, `GrAppv`, `SBA_Appv`): stored as text with `$` and commas — must be parsed to float
- Date columns (`ApprovalDate`, `DisbursementDate`, `ChgOffDate`): stored as strings — must be parsed to datetime

## 5. Numeric anomalies observed
- `NoEmp` min = 0 (impossible — business must have ≥1 employee)
- `NoEmp` max = 9999 (placeholder value)
- `Term` max = 569 months (~47 years) — implausibly long