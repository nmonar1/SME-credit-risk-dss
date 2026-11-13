import streamlit as st
import joblib
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_connection, init_db, migrate_db, authenticate, is_user_active
from labels import NAICS_LABELS
from screens_officer import submit_application_screen, my_applications_screen
from screens_admin import manage_users_screen, system_performance_screen
from theme import inject_css, sidebar_brand, login_art

st.set_page_config(page_title="Credit Risk DSS", page_icon="🏦", layout="wide")
inject_css()

if not os.path.exists("database/credit_risk.db"):
    init_db()

conn = get_connection()
migrate_db(conn)
sector_list = joblib.load("models/sector_list.pkl")

if "user" not in st.session_state:
    st.session_state.user = None

# an account deactivated while its owner is signed in is signed out on the next click
if st.session_state.user is not None and not is_user_active(conn, st.session_state.user["user_id"]):
    st.session_state.clear()
    st.session_state["login_notice"] = "Your account has been deactivated. Contact your administrator."
    st.session_state.user = None


def login_page():
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        login_art()
    with right:
        st.markdown("<div style='height:70px'></div>", unsafe_allow_html=True)
        st.markdown("## Welcome back")
        st.write("Sign in to continue.")
        notice = st.session_state.pop("login_notice", None)
        if notice:
            st.warning(notice)
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", use_container_width=True)
        if submitted:
            user = authenticate(conn, username, password)
            if user is None:
                st.error("Invalid username or password.")
            elif not user["active"]:
                st.error("This account has been deactivated. Contact your administrator.")
            else:
                st.session_state.user = {"user_id": user["user_id"], "role": user["role"]}
                st.rerun()


def sidebar_nav(items):
    sidebar_brand("Loan Officer" if st.session_state.user["role"] == "loan_officer" else "Administrator")
    if "pending_nav" in st.session_state:
        st.session_state["nav"] = st.session_state.pop("pending_nav")
    choice = st.sidebar.radio("Navigate", items, key="nav", label_visibility="collapsed")
    st.sidebar.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
    if st.sidebar.button("Sign out"):
        st.session_state.clear()
        st.rerun()
    return choice


if st.session_state.user is None:
    login_page()
elif st.session_state.user["role"] == "loan_officer":
    choice = sidebar_nav(["Submit Application", "My Applications"])
    if choice == "Submit Application":
        submit_application_screen(conn, sector_list, NAICS_LABELS)
    else:
        my_applications_screen(conn, NAICS_LABELS)
elif st.session_state.user["role"] == "admin":
    choice = sidebar_nav(["Manage Users", "System Performance"])
    if choice == "Manage Users":
        manage_users_screen(conn)
    else:
        system_performance_screen(conn)