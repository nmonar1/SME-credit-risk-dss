import json
import joblib
import shap

from labels import NAICS_LABELS, FEATURE_LABELS
from report_text import PORTFOLIO_DEFAULT_RATE, BAND_INFO, BAND_MEANING, pct_text

rf = joblib.load("models/random_forest_model.pkl")
iso = joblib.load("models/isotonic_calibrator.pkl")
sector_list = joblib.load("models/sector_list.pkl")
with open("models/risk_thresholds.json") as f:
    THRESHOLDS = json.load(f)
explainer = shap.TreeExplainer(rf)
print("Explainer loaded from saved model and rebuilt.")


def classify_risk(calibrated_prob, thresholds=THRESHOLDS):
    if calibrated_prob < thresholds["low_max"]:
        return "Low"
    elif calibrated_prob < thresholds["high_min"]:
        return "Moderate"
    return "Elevated"


def _describe_value(feature, row):
    v = row[feature].iloc[0]
    if feature == "GrAppv":
        return f"${v:,.0f}"
    if feature == "NoEmp":
        return f"{int(v)}"
    if feature == "NewExist":
        return "new business" if v == 2.0 else "established business"
    if feature == "NAICS_Sector":
        return NAICS_LABELS.get(sector_list[int(v)], "Unknown")
    return str(v)


def _strength(share):
    if share >= 0.5:
        return "the main driver"
    if share >= 0.2:
        return "a moderate influence"
    if share >= 0.05:
        return "a small influence"
    return "almost no effect"


def build_explanation(prob, risk_class, ranked, feature_row):
    total = sum(abs(v) for _, v in ranked) or 1.0
    band = BAND_INFO[risk_class]
    lines = [
        f"Among past SBA loans that the model scored like this one, {'about ' if prob >= 0.01 else ''}**{pct_text(prob)}** defaulted. "
        f"The average across all loans in the data is {PORTFOLIO_DEFAULT_RATE:.0%}. "
        f"This places the application in the **{risk_class}** band.",
        "",
        "**What moved the score for this application:**",
        "",
    ]
    for feat, val in ranked:
        direction = "pushed the score up (more risk)" if val > 0 else "pushed the score down (less risk)"
        lines.append(
            f"- {FEATURE_LABELS[feat]} ({_describe_value(feat, feature_row)}) {direction}: "
            f"{_strength(abs(val) / total)}."
        )
    lines += [
        "",
        f"The {risk_class} band is the {band['share']:.0%} of applications with "
        f"{'the lowest' if risk_class == 'Low' else 'higher' if risk_class == 'Moderate' else 'the highest'} "
        f"scores. Historically about {band['default_rate']:.0%} of loans in this band still defaulted. "
        f"{BAND_MEANING[risk_class]}",
        "",
        "This is decision support, not a decision.",
    ]
    return "\n".join(lines)


def explain_application(feature_row):
    """feature_row: 1-row DataFrame with columns NoEmp, GrAppv, NewExist, NAICS_Sector
    (NAICS_Sector already encoded as its integer code)."""
    raw = rf.predict_proba(feature_row)[0, 1]
    prob = float(iso.predict([raw])[0])
    risk_class = classify_risk(prob)

    sv = explainer.shap_values(feature_row)
    contrib = sv[1][0] if isinstance(sv, list) else sv[0, :, 1]
    contribs = {name: float(v) for name, v in zip(feature_row.columns, contrib)}
    ranked = sorted(contribs.items(), key=lambda kv: abs(kv[1]), reverse=True)

    return {
        "risk_score": round(prob, 4),
        "risk_classification": risk_class,
        "plain_language_summary": build_explanation(prob, risk_class, ranked, feature_row),
        "top_features": json.dumps([{"feature": FEATURE_LABELS[f], "value": round(v, 4)} for f, v in ranked]),
    }


if __name__ == "__main__":
    import pandas as pd
    code = sector_list.index("44")
    for name, amount in [("Small loan ($50k)", 50000.0), ("Large loan ($500k)", 500000.0)]:
        row = pd.DataFrame([{"NoEmp": 5, "GrAppv": amount, "NewExist": 2.0, "NAICS_Sector": code}])
        result = explain_application(row)
        print(f"=== {name} ===")
        print("score:", result["risk_score"], "| band:", result["risk_classification"])
        print(result["plain_language_summary"])
        print()