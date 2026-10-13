from database import get_connection, verify_login, save_application, save_risk_assessment, save_decision
from shap_explainer import explain_application
import pandas as pd
import joblib

conn = get_connection()
user = verify_login(conn, "j.mwangi", "ChangeThisPassword2")
print("Logged in as:", user)

officer_id = conn.execute("SELECT officer_id FROM loan_officers WHERE user_id=?", (user["user_id"],)).fetchone()[0]

app_id = save_application(conn, officer_id, {
    "business_name": "Jua Kali Hardware Ltd", "industry_type": "44",
    "num_employees": 5, "business_age": 2, "loan_amount": 50000.0,
    "loan_term": 24, "application_date": "2026-10-01"
})
print("Application saved, id:", app_id)

sector_list = joblib.load("models/sector_list.pkl")
sector_code = sector_list.index("44")
feature_row = pd.DataFrame([{"NoEmp": 5, "GrAppv": 50000.0, "NewExist": 2.0, "NAICS_Sector": sector_code}])
result = explain_application(feature_row)
print("Risk assessment:", result)

ra_id = save_risk_assessment(conn, app_id, result)
print("Risk assessment saved, id:", ra_id)

save_decision(conn, app_id, officer_id, "Approved")
print("Decision recorded")

row = conn.execute("""
    SELECT la.business_name, la.application_status, ra.risk_score, ra.risk_classification, d.decision
    FROM loan_applications la
    JOIN risk_assessments ra ON ra.application_id = la.application_id
    JOIN decisions d ON d.application_id = la.application_id
    WHERE la.application_id = ?
""", (app_id,)).fetchone()
print("\nFull record:", row)