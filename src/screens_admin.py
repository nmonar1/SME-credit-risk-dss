import os
import re
import sqlite3
import json
import pandas as pd
import streamlit as st

from database import (list_users, add_user, set_user_active, reset_password, update_user_detail,
                      get_admin_id, usage_summary, band_counts, applications_per_day)
from metrics import scoring_stats
from report_text import BAND_INFO
from theme import (page_header, kpi_cards, band_donut, per_day_chart, model_comparison_chart,
                   BRAND, LOW, MODERATE, ELEVATED, INK)

ROLE_LABELS = {"loan_officer": "Loan Officer", "admin": "Administrator"}
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,50}$")

# (town, county) - edit this list to match the branches you want to show
_BRANCH_TOWNS = [
    ("CBD", "Nairobi"), ("Westlands", "Nairobi"), ("Kilimani", "Nairobi"), ("Karen", "Nairobi"),
    ("Eastleigh", "Nairobi"), ("Thika", "Kiambu"), ("Ruiru", "Kiambu"), ("Kitengela", "Kajiado"),
    ("Machakos Town", "Machakos"), ("Nakuru Town", "Nakuru"), ("Naivasha", "Nakuru"),
    ("Eldoret", "Uasin Gishu"), ("Kisumu Central", "Kisumu"), ("Kakamega Town", "Kakamega"),
    ("Kisii Town", "Kisii"), ("Mombasa Island", "Mombasa"), ("Nyali", "Mombasa"), ("Malindi", "Kilifi"),
    ("Nyeri Town", "Nyeri"), ("Nanyuki", "Laikipia"), ("Meru Town", "Meru"), ("Embu Town", "Embu"),
    ("Kericho Town", "Kericho"), ("Garissa Town", "Garissa"),
]
BRANCHES = [f"{t}, {c} County" for t, c in _BRANCH_TOWNS]
ACCESS_LEVELS = ["Full access", "Limited access"]


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


def _options_with(current, options):
    """Keep an older value (e.g. a branch saved as just 'Westlands') selectable instead of crashing."""
    return options if (not current or current in options) else [current] + options


def manage_users_screen(conn):
    page_header("Manage Users", "Accounts, branches and access")
    _show_flash()
    me = st.session_state.user
    my_admin_id = get_admin_id(conn, me["user_id"])
    users = list_users(conn)

    kpi_cards([("Total accounts", len(users), INK),
               ("Active", sum(1 for u in users if u["is_active"]), LOW),
               ("Loan officers", sum(1 for u in users if u["role"] == "loan_officer"), BRAND),
               ("Deactivated", sum(1 for u in users if not u["is_active"]), ELEVATED)])

    df_users = pd.DataFrame([{
        "ID": u["user_id"], "Username": u["username"], "Role": ROLE_LABELS.get(u["role"], u["role"]),
        "Branch / access level": u["detail"] or "", "Managed by": u["managed_by"] or "",
        "Applications": "-" if u["applications"] is None else str(u["applications"]),
        "Status": "🟢 Active" if u["is_active"] else "🔴 Deactivated"} for u in users])

    edited_df = st.data_editor(
        df_users, hide_index=True, use_container_width=True,
        disabled=["ID", "Username", "Role", "Branch / access level", "Managed by", "Applications"],
        column_config={"Status": st.column_config.SelectboxColumn(
            "Status", options=["🟢 Active", "🔴 Deactivated"], required=True)},
        key="user_editor")

    for idx, row in edited_df.iterrows():
        original_status = df_users.iloc[idx]["Status"]
        new_status = row["Status"]
        if new_status != original_status:
            if row["ID"] == me["user_id"]:
                st.error("You cannot deactivate your own account.")
                st.rerun()
            else:
                set_user_active(conn, row["ID"], new_status == "🟢 Active")
                _flash(f"{row['Username']} is now {new_status.split(' ', 1)[1].lower()}.")
                st.rerun()

    # ---------------- add a user ----------------
    st.subheader("Add a user")
    role_label = st.radio("Role", ["Loan Officer", "Administrator"], horizontal=True, key="new_role")
    is_officer = role_label == "Loan Officer"
    with st.form("add_user_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        username = c1.text_input("Username")
        password = c2.text_input("Temporary password", type="password")
        detail = c3.selectbox("Branch" if is_officer else "Access level", BRANCHES if is_officer else ACCESS_LEVELS)
        submitted = st.form_submit_button("Create account")
    if submitted:
        username = username.strip()
        if not USERNAME_RE.match(username):
            st.error("Username must be 3 to 50 characters: letters, digits, dot, dash or underscore.")
        elif _password_problem(password):
            st.error(_password_problem(password))
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
    col1, col2 = st.columns(2)

    with col1:
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
        is_off = user["role"] == "loan_officer"
        label = "Branch" if is_off else "Access level"
        opts = _options_with(user["detail"], BRANCHES if is_off else ACCESS_LEVELS)
        idx = opts.index(user["detail"]) if user["detail"] in opts else 0
        new_detail = st.selectbox(label, opts, index=idx, key=f"det_{uid}")
        if st.button("Save", key=f"detb_{uid}"):
            update_user_detail(conn, uid, new_detail)
            _flash(f"{label} updated for {user['username']}.")
            st.rerun()


def system_performance_screen(conn):
    page_header("System Performance", "How the system is being used")
    s = usage_summary(conn)
    decided = s["approved"] + s["rejected"]

    kpi_cards([("Applications today", s["today"], BRAND), ("Last 7 days", s["last7"], BRAND),
               ("All time", s["total"], INK), ("Pending decisions", s["pending"], MODERATE)])
    kpi_cards([("Approved", s["approved"], LOW), ("Rejected", s["rejected"], ELEVATED),
               ("Approval rate", f"{s['approved'] / decided:.0%}" if decided else "n/a", INK),
               ("Active accounts", f"{s['users_active']} of {s['users_total']}", INK)])

    left, right = st.columns([1.6, 1])
    with left:
        st.subheader("Applications per day")
        per_day_chart(applications_per_day(conn, 14))
    with right:
        st.subheader("Risk band mix")
        counts = band_counts(conn)
        band_donut(counts)

    total = sum(counts.values())
    st.dataframe(pd.DataFrame([{
        "Band": band, "Applications": counts.get(band, 0),
        "Share so far": f"{counts.get(band, 0) / total:.0%}" if total else "n/a",
        "Share in the test data": f"{BAND_INFO[band]['share']:.0%}"} for band in ["Low", "Moderate", "Elevated"]]),
        hide_index=True, use_container_width=True)

    st.subheader("Scoring speed")
    stats = scoring_stats()
    if stats is None:
        st.info("Nothing scored yet in this session.")
    else:
        kpi_cards([("Average time", f"{stats['avg']:.0f} ms", BRAND), ("Slowest", f"{stats['max']:.0f} ms", MODERATE),
                   ("Applications scored", stats["count"], INK)])

    st.subheader("Model quality")
    path = "models/model_results.csv"
    if os.path.exists(path):
        rf_row = pd.read_csv(path).query("Model == 'Random Forest'")
        if not rf_row.empty:
            r = rf_row.iloc[0]
            kpi_cards([("ROC-AUC", f"{r['ROC-AUC']:.3f}", BRAND), ("PR-AUC", f"{r['PR-AUC']:.3f}", BRAND),
                       ("Precision", f"{r['Precision']:.3f}", INK), ("Recall", f"{r['Recall']:.3f}", INK)])
    else:
        st.info("Model results file not found.")

    st.subheader("Model comparison")
    model_comparison_chart()