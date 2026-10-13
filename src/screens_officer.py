import json
import os
import time
import pandas as pd
import streamlit as st

from database import save_application, save_risk_assessment, save_decision, list_applications, get_application
from shap_explainer import explain_application
from metrics import record_scoring_time
from report_text import PORTFOLIO_DEFAULT_RATE, BAND_INFO, MODEL_NOTE, pct_short

PRESET_PATH = "models/demo_presets.json"
FORM_DEFAULTS = {"f_name": "", "f_emp": 0, "f_age": 0, "f_amt": 50000.0, "f_term": 60}
FORM_KEYS = list(FORM_DEFAULTS) + ["f_sector", "f_date"]


def _officer_id(conn):
    row = conn.execute("SELECT officer_id FROM loan_officers WHERE user_id=?",
                       (st.session_state.user["user_id"],)).fetchone()
    return row[0]


def _load_presets():
    if os.path.exists(PRESET_PATH):
        with open(PRESET_PATH) as f:
            return json.load(f)
    return {}


def _apply_preset(preset):
    st.session_state["f_name"] = preset["business_name"]
    st.session_state["f_sector"] = preset["sector"]
    st.session_state["f_emp"] = int(preset["num_employees"])
    st.session_state["f_age"] = int(preset["business_age"])
    st.session_state["f_amt"] = float(preset["loan_amount"])
    st.session_state["f_term"] = int(preset["loan_term"])


def submit_application_screen(conn, sector_list, naics_labels):
    st.header("New SME Loan Application")
    officer_id = _officer_id(conn)

    for key, default in FORM_DEFAULTS.items():
        st.session_state.setdefault(key, default)
    st.session_state.setdefault("f_sector", sector_list[0])

    presets = _load_presets()
    if presets:
        st.caption("Demo examples: fill the form with a typical application from each risk band.")
        cols = st.columns(len(presets))
        for col, (label, preset) in zip(cols, presets.items()):
            col.button(f"Load example: {label}", key=f"preset_{label}",
                       on_click=_apply_preset, args=(preset,))

    c1, c2 = st.columns(2)
    with c1:
        business_name = st.text_input("Business Name", key="f_name")
        sector_choice = st.selectbox("Industry Sector", sector_list, key="f_sector",
                                     format_func=lambda c: f"{c} - {naics_labels.get(c, 'Unknown')}")
        num_employees = st.number_input("Number of Employees", min_value=0, step=1, key="f_emp")
        business_age = st.number_input("Business Age (years)", min_value=0, step=1, key="f_age")
    with c2:
        loan_amount = st.number_input("Loan Amount (USD)", min_value=1000.0, max_value=5500000.0,
                                      step=1000.0, key="f_amt")
        loan_term = st.number_input("Loan Term (months)", min_value=1, step=1, key="f_term")
        application_date = st.date_input("Application Date", key="f_date")
    

    if st.button("Submit Application", type="primary"):
        if not business_name.strip():
            st.error("Business name is required.")
            return
        app_id = save_application(conn, officer_id, {
            "business_name": business_name.strip(), "industry_type": sector_choice,
            "num_employees": int(num_employees), "business_age": int(business_age),
            "loan_amount": float(loan_amount), "loan_term": int(loan_term),
            "application_date": str(application_date)})

        new_exist = 2.0 if business_age <= 2 else 1.0
        feature_row = pd.DataFrame([{"NoEmp": num_employees, "GrAppv": loan_amount,
                                     "NewExist": new_exist,
                                     "NAICS_Sector": sector_list.index(sector_choice)}])
        started = time.perf_counter()
        result = explain_application(feature_row)
        record_scoring_time((time.perf_counter() - started) * 1000)
        save_risk_assessment(conn, app_id, result)

        for k in FORM_KEYS:
            st.session_state.pop(k, None)
        st.session_state.pending_open = app_id
        st.session_state.pending_nav = "My Applications"
        st.rerun()


def _contribution_chart(top_features):
    try:
        data = pd.DataFrame(json.loads(top_features)).set_index("feature")
    except (ValueError, TypeError, KeyError):
        st.caption(top_features or "")      # older rows stored a plain text string
        return
    st.caption("Influence of each input on this score: bars to the right push the risk up, "
               "bars to the left push it down.")
    st.bar_chart(data, horizontal=True)


def _legend():
    with st.expander("How to read this report"):
        st.markdown(
            "| Band | Who falls in it | Past loans in this band that defaulted |\n|---|---|---|\n"
            f"| Low | the lowest-scoring {BAND_INFO['Low']['share']:.0%} of applications | {BAND_INFO['Low']['default_rate']:.0%} |\n"
            f"| Moderate | the next {BAND_INFO['Moderate']['share']:.0%} | {BAND_INFO['Moderate']['default_rate']:.0%} |\n"
            f"| Elevated | the highest-scoring {BAND_INFO['Elevated']['share']:.0%} | {BAND_INFO['Elevated']['default_rate']:.0%} |\n\n"
            f"The average default rate across all loans in the data is {PORTFOLIO_DEFAULT_RATE:.1%}."
        )
        st.markdown(MODEL_NOTE)


def render_report(conn, officer_id, application_id, naics_labels):
    row = get_application(conn, application_id, officer_id)
    if row is None:
        st.error("Application not found.")
        return

    status = row["application_status"]
    st.subheader(f"{row['business_name']} (application #{application_id})")
    st.caption(f"{row['application_date']} | {naics_labels.get(row['industry_type'], row['industry_type'])} | "
               f"${row['loan_amount']:,.0f} | Status: {status}")

    if row["risk_score"] is None:
        st.warning("No risk assessment is stored for this application.")
    else:
        score = float(row["risk_score"])
        c1, c2 = st.columns(2)
        c1.metric("Risk band", row["risk_classification"])
        c2.metric("Similar past loans that defaulted", pct_short(score),
                  delta=f"{(score - PORTFOLIO_DEFAULT_RATE) * 100:+.1f} pts vs average ({PORTFOLIO_DEFAULT_RATE:.1%})",
                  delta_color="inverse")
        st.markdown(row["plain_language_summary"])
        _contribution_chart(row["top_features"])
        _legend()

    if status == "Pending":
        st.subheader("Record your decision")
        decision = st.radio("Decision", ["Approve", "Reject"], key=f"dec_{application_id}", horizontal=True)
        note = st.text_area("Reason (required)" if decision == "Reject" else "Notes (optional)",
                            key=f"note_{application_id}", max_chars=255)
        if st.button("Confirm Decision", key=f"confirm_{application_id}"):
            if decision == "Reject" and not note.strip():
                st.error("A reason is required to reject an application.")
            else:
                label = "Approved" if decision == "Approve" else "Rejected"
                save_decision(conn, application_id, officer_id, label, note.strip() or None)
                st.rerun()
    else:
        detail = f" ({row['decision_reason']})" if row["decision_reason"] else ""
        st.success(f"Decision recorded: {status}{detail}")

    if row["risk_score"] is not None:
        report = (f"SME Credit Risk Report\nApplication #{application_id}\nBusiness: {row['business_name']}\n"
                  f"Loan Amount: ${row['loan_amount']:,.2f}\nRisk band: {row['risk_classification']}\n"
                  f"Similar past loans that defaulted: {pct_short(float(row['risk_score']))}\nStatus: {status}\n\n"
                  f"{row['plain_language_summary'].replace('**', '')}\n")
        st.download_button("Download Report", report, file_name=f"risk_report_app{application_id}.txt",
                           key=f"dl_{application_id}")


def my_applications_screen(conn, naics_labels):
    st.header("My Applications")
    officer_id = _officer_id(conn)
    rows = list_applications(conn, officer_id)
    if not rows:
        st.info("You have not submitted any applications yet.")
        return

    status_filter = st.radio("Show", ["All", "Pending", "Approved", "Rejected"], horizontal=True)
    shown = [r for r in rows if status_filter == "All" or r["application_status"] == status_filter]
    if not shown:
        st.info(f"No {status_filter.lower()} applications.")
        return

    st.dataframe(pd.DataFrame([{
        "ID": r["application_id"], "Business": r["business_name"],
        "Sector": naics_labels.get(r["industry_type"], r["industry_type"]),
        "Loan amount": f"${r['loan_amount']:,.0f}", "Risk band": r["risk_classification"],
        "Past default rate": pct_short(float(r["risk_score"])) if r["risk_score"] is not None else "",
        "Status": r["application_status"], "Date": r["application_date"]} for r in shown]),
        hide_index=True)

    ids = [r["application_id"] for r in shown]
    # labels must not contain the status: if they did, approving an application would change the
    # label and Streamlit would treat the selectbox as a new widget and jump to another application
    names = {r["application_id"]: f"#{r['application_id']} - {r['business_name']}" for r in shown}

    # Decide which application the dropdown should show BEFORE the widget is created.
    # (Do not pass index= to the selectbox: a changing index makes Streamlit forget the user's choice.)
    pending = st.session_state.pop("pending_open", None)
    if pending is not None:
        st.session_state["open_select"] = pending
    elif "open_select" not in st.session_state and st.session_state.get("open_app_id") in ids:
        st.session_state["open_select"] = st.session_state["open_app_id"]
    if st.session_state.get("open_select") not in ids:
        st.session_state["open_select"] = ids[0]

    selected = st.selectbox("Open application", ids, key="open_select", format_func=lambda i: names[i])
    st.session_state.open_app_id = selected
    st.divider()
    render_report(conn, officer_id, selected, naics_labels)