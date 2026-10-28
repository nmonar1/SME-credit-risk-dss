import os
import re
import sqlite3
from datetime import datetime
import json
import pandas as pd
import streamlit as st

from database import (list_users, add_user, set_user_active, reset_password, update_user_detail,
                      get_admin_id, usage_summary, band_counts, applications_per_day)
from metrics import scoring_stats
from report_text import BAND_INFO

ROLE_LABELS = {"loan_officer": "Loan Officer", "admin": "Administrator"}
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,50}$")


def _flash(message):
    st.session_state["flash"] = message


def _show_flash():
    message = st.session_state.pop("flash", None)
    if message:
        st.success(message)


def _password_problem(password):
    if len(password) < 8:
        return "The password must be at least 8 characters."
    if len(password.encode()) > 72:
        return "The password is too long (maximum 72 bytes)."
    return None


def manage_users_screen(conn):
    st.header("Manage Users")
    _show_flash()
    me = st.session_state.user
    my_admin_id = get_admin_id(conn, me["user_id"])
    users = list_users(conn)

    # Build the dataframe for the editor
    df_users = pd.DataFrame([{
        "ID": u["user_id"], "Username": u["username"], "Role": ROLE_LABELS.get(u["role"], u["role"]),
        "Branch / access level": u["detail"] or "", "Managed by": u["managed_by"] or "",
        "Applications": "-" if u["applications"] is None else str(u["applications"]),
        "Status": "Active" if u["is_active"] else "Deactivated"} for u in users])

    # Render the interactive data editor
    edited_df = st.data_editor(
        df_users,
        hide_index=True,
        disabled=["ID", "Username", "Role", "Branch / access level", "Managed by", "Applications"],
        column_config={
            "Status": st.column_config.SelectboxColumn(
                "Status",
                help="Change this dropdown to deactivate or reactivate the account.",
                options=["Active", "Deactivated"],
                required=True,
            )
        },
        key="user_editor"
    )

    # Check if any statuses were changed
    for idx, row in edited_df.iterrows():
        original_status = df_users.iloc[idx]["Status"]
        new_status = row["Status"]
        
        if new_status != original_status:
            target_user_id = row["ID"]
            target_username = row["Username"]
            
            # Prevent admins from deactivating themselves
            if target_user_id == me["user_id"]:
                st.error("You cannot deactivate your own account.")
                st.rerun()
            else:
                set_user_active(conn, target_user_id, new_status == "Active")
                _flash(f"{target_username} status updated to {new_status}.")
                st.rerun()

    # ---------------- add a user ----------------
    st.subheader("Add a user")
    role_label = st.radio("Role", ["Loan Officer", "Administrator"], horizontal=True, key="new_role")
    is_officer = role_label == "Loan Officer"
    with st.form("add_user_form", clear_on_submit=True):
        username = st.text_input("Username")
        password = st.text_input("Temporary password (8 to 72 characters)", type="password")
        detail = st.text_input("Branch office" if is_officer else "Access level", value="" if is_officer else "full")
        submitted = st.form_submit_button("Create account")
    if submitted:
        username, detail = username.strip(), detail.strip()
        if not USERNAME_RE.match(username):
            st.error("Username must be 3 to 50 characters: letters, digits, dot, dash or underscore.")
        elif _password_problem(password):
            st.error(_password_problem(password))
        elif not detail or len(detail) > 100:
            st.error(f"{'Branch office' if is_officer else 'Access level'} is required (up to 100 characters).")
        else:
            try:
                add_user(conn, username, password, "loan_officer" if is_officer else "admin", detail, my_admin_id)
            except sqlite3.IntegrityError:
                st.error(f"The username '{username}' is already taken.")
            else:
                _flash(f"Account created for {username} ({role_label}).")
                st.rerun()

    # ---------------- edit a user ----------------
    st.subheader("Edit a user")
    by_id = {u["user_id"]: u for u in users}
    uid = st.selectbox("User", list(by_id), key="edit_user",
                       format_func=lambda i: f"{by_id[i]['username']} ({ROLE_LABELS.get(by_id[i]['role'], by_id[i]['role'])})")
    user = by_id[uid]
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Reset password**")
        new_pw = st.text_input("New temporary password", type="password", key=f"rp_{uid}")
        if st.button("Reset password", key=f"rpb_{uid}"):
            if _password_problem(new_pw):
                st.error(_password_problem(new_pw))
            else:
                reset_password(conn, uid, new_pw)
                st.session_state.pop(f"rp_{uid}", None)
                _flash(f"Password reset for {user['username']}.")
                st.rerun()

    with col2:
        st.markdown("**Branch / access level**")
        label = "Branch office" if user["role"] == "loan_officer" else "Access level"
        new_detail = st.text_input(label, value=user["detail"] or "", key=f"det_{uid}")
        if st.button("Save", key=f"detb_{uid}"):
            if not new_detail.strip() or len(new_detail.strip()) > 100:
                st.error(f"{label} is required (up to 100 characters).")
            else:
                update_user_detail(conn, uid, new_detail.strip())
                _flash(f"{label} updated for {user['username']}.")
                st.rerun()

    with col3:
        st.markdown("**Account status**")
        st.caption("Use the dropdown in the table above to change a user's status.")

    st.caption("Accounts are deactivated rather than deleted, so the applications an officer handled stay on record.")


def system_performance_screen(conn):
    st.header("System Performance")
    s = usage_summary(conn)

    st.subheader("Usage")
    c = st.columns(4)
    c[0].metric("Applications today", s["today"])
    c[1].metric("Last 7 days", s["last7"])
    c[2].metric("All time", s["total"])
    c[3].metric("Pending decisions", s["pending"])
    decided = s["approved"] + s["rejected"]
    c = st.columns(4)
    c[0].metric("Approved", s["approved"])
    c[1].metric("Rejected", s["rejected"])
    c[2].metric("Approval rate", f"{s['approved'] / decided:.0%}" if decided else "n/a")
    c[3].metric("Active accounts", f"{s['users_active']} of {s['users_total']}")

    st.caption("Applications per day (by application date, last 14 days)")
    per_day = pd.DataFrame(applications_per_day(conn, 14), columns=["Date", "Applications"]).set_index("Date")
    st.bar_chart(per_day)
    st.caption("Admins see counts only, never the details of an individual application.")

    st.subheader("Risk band mix")
    counts = band_counts(conn)
    total = sum(counts.values())
    st.dataframe(pd.DataFrame([{
        "Band": band, "Applications": counts.get(band, 0),
        "Share so far": f"{counts.get(band, 0) / total:.0%}" if total else "n/a",
        "Share in the test data": f"{BAND_INFO[band]['share']:.0%}"} for band in ["Low", "Moderate", "Elevated"]]),
        hide_index=True)
    st.caption("A handful of applications says very little. A large, lasting gap from the test-data shares would "
               "suggest today's applicants differ from the loans the model was trained on.")

    st.subheader("Model scoring speed (since the server last started)")
    stats = scoring_stats()
    if stats is None:
        st.info("No applications have been scored since the server started.")
    else:
        c = st.columns(3)
        c[0].metric("Average scoring time", f"{stats['avg']:.0f} ms")
        c[1].metric("Slowest", f"{stats['max']:.0f} ms")
        c[2].metric("Applications scored", stats["count"])

    st.subheader("Model quality (measured on held-out test data when the model was trained)")
    path = "models/model_results.csv"
    if os.path.exists(path):
        results = pd.read_csv(path)
        rf_row = results[results["Model"] == "Random Forest"]
        if not rf_row.empty:
            r = rf_row.iloc[0]
            c = st.columns(4)
            c[0].metric("ROC-AUC", f"{r['ROC-AUC']:.3f}")
            c[1].metric("PR-AUC", f"{r['PR-AUC']:.3f}")
            c[2].metric("Precision", f"{r['Precision']:.3f}")
            c[3].metric("Recall", f"{r['Recall']:.3f}")
    else:
        st.info("models/model_results.csv was not found, so model quality is not shown.")
    model_path = "models/random_forest_model.pkl"
    notes = []
    if os.path.exists(model_path):
        notes.append(f"Model file last saved: {datetime.fromtimestamp(os.path.getmtime(model_path)):%d %b %Y %H:%M}")
    if os.path.exists("models/risk_thresholds.json"):
        with open("models/risk_thresholds.json") as f:
            th = json.load(f)
        notes.append(f"Band cut-offs: Low below {th['low_max']:.3f}, Elevated from {th['high_min']:.3f}")
    if notes:
        st.caption(" | ".join(notes))