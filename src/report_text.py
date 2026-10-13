# Numbers below come from the Phase 6 calibration run on the held-out test set (138,928 loans).
# If you re-run calibrate.py and the bucket results change, update them here.
PORTFOLIO_DEFAULT_RATE = 0.203

BAND_INFO = {
    "Low":      {"share": 0.791, "default_rate": 0.163},
    "Moderate": {"share": 0.182, "default_rate": 0.346},
    "Elevated": {"share": 0.026, "default_rate": 0.414},
}

BAND_MEANING = {
    "Low": "Low means lower than average risk, not no risk.",
    "Moderate": "Moderate is clearly above the Low band and deserves a closer manual look.",
    "Elevated": "Elevated is the highest band this model produces.",
}

MODEL_NOTE = (
    "The model uses only four inputs: loan amount, number of employees, new or established "
    "business, and industry sector. It cannot see credit history, collateral, cash flow or "
    "repayment capacity, and it was trained on US SBA loans approved between 1984 and 2014. "
    "It separates repaid from defaulted loans only modestly (ROC-AUC about 0.68), so treat it "
    "as one input to your decision, not the decision itself."
)


def pct_text(p):
    """For sentences. Isotonic calibration can output exactly 0, which means 'nothing defaulted in the
    calibration data at this score', not 'zero risk', so never print 0%."""
    return "less than 1%" if p < 0.01 else f"{p:.0%}"


def pct_short(p):
    """For metrics and tables."""
    return "<1%" if p < 0.01 else f"{p:.1%}"