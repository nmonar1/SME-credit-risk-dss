import streamlit as st
import joblib
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import (
    get_connection,
    init_db,
    migrate_db,
    authenticate,
    get_session_status,
    change_password,
    get_admin_access_level
)

from labels import NAICS_LABELS

from screens_officer import (
    submit_application_screen,
    my_applications_screen
)

from screens_admin import (
    manage_users_screen,
    system_performance_screen,
    user_directory_screen
)

from theme import (
    inject_css,
    sidebar_brand,
    login_art,
    page_header
)


# ---------- Application configuration ----------

st.set_page_config(
    page_title="Credit Risk DSS",
    page_icon="🦉",
    layout="wide"
)

inject_css()


# ---------- Database and model resources ----------

if not os.path.exists("database/credit_risk.db"):
    init_db()

conn = get_connection()
migrate_db(conn)

sector_list = joblib.load("models/sector_list.pkl")


# ---------- Session management ----------

if "user" not in st.session_state:
    st.session_state.user = None


def end_session(notice=None, notice_type="warning"):
    """Clears the current session and returns the user to login."""

    st.session_state.clear()
    st.session_state.user = None

    if notice:
        st.session_state["login_notice"] = notice
        st.session_state["login_notice_type"] = notice_type

    st.rerun()


def validate_session():
    """Checks whether the current login session is still valid."""

    user = st.session_state.user

    if user is None:
        return

    status = get_session_status(
        conn,
        user["user_id"]
    )

    if status is None:
        end_session(
            "Your account is no longer available. "
            "Contact your administrator."
        )

    if not status["active"]:
        end_session(
            "Your account has been deactivated. "
            "Contact your administrator."
        )

    if (
        user.get("session_version") != status["session_version"]
        or user.get("role") != status["role"]
    ):
        end_session(
            "Your account details have changed. "
            "Please sign in again."
        )

    st.session_state.user["must_change_password"] = (
        status["must_change_password"]
    )

    if status["role"] == "admin":
        access_level = get_admin_access_level(
            conn,
            user["user_id"]
        )

        if access_level not in (
            "Full access",
            "Limited access"
        ):
            end_session(
                "Your administrator access level is unavailable. "
                "Contact your administrator."
            )

        st.session_state.user["access_level"] = access_level


validate_session()


# ---------- Login screen ----------

def login_page():
    left, right = st.columns(
        [1.15, 1],
        gap="large"
    )

    with left:
        login_art()

    with right:
        st.markdown(
            "<div style='height:70px'></div>",
            unsafe_allow_html=True
        )

        st.markdown("## Welcome back")
        st.write("Sign in to continue.")

        notice = st.session_state.pop(
            "login_notice", None
        )

        notice_type = st.session_state.pop(
            "login_notice_type", "warning"
        )

        if notice:
            if notice_type == "success":
                st.success(notice)
            else:
                st.warning(notice)

        with st.form("login_form"):
            username = st.text_input("Username")

            password = st.text_input(
                "Password",
                type="password"
            )

            submitted = st.form_submit_button(
                "Sign in",
                use_container_width=True
            )

        if submitted:
            user = authenticate(
                conn,
                username,
                password
            )

            if user is None:
                st.error(
                    "Invalid username or password."
                )

            elif not user["active"]:
                st.error(
                    "This account has been deactivated. "
                    "Contact your administrator."
                )

            elif user["role"] not in (
                "loan_officer", "admin"
            ):
                st.error(
                    "This account has an invalid role. "
                    "Contact your administrator."
                )

            else:
                st.session_state.user = {
                    "user_id": user["user_id"],
                    "role": user["role"],
                    "must_change_password": (
                        user["must_change_password"]
                    ),
                    "session_version": (
                        user["session_version"]
                    )
                }

                st.rerun()


# ---------- Password change form ----------

def password_change_form(required=False):
    """Shared password change form for both user roles."""

    if required:
        st.warning(
            "You are using a temporary password. "
            "Set a personal password before accessing your dashboard."
        )

    else:
        st.write(
            "Update your password to keep your account secure."
        )

    with st.form(
        "required_password_form"
        if required
        else "voluntary_password_form"
    ):
        current_password = st.text_input(
            "Temporary password"
            if required
            else "Current password",
            type="password"
        )

        new_password = st.text_input(
            "New password",
            type="password"
        )

        confirm_password = st.text_input(
            "Confirm new password",
            type="password"
        )

        st.markdown("**Password requirements**")

        st.caption(
            "• At least 8 characters\n\n"
            "• No more than 72 bytes\n\n"
            "• Different from your current password\n\n"
            "• Both new password entries must match"
        )

        submitted = st.form_submit_button(
            "Update password",
            use_container_width=True
        )

    if submitted:

        if not all([
            current_password,
            new_password,
            confirm_password
        ]):
            st.error("Please complete all fields.")

        elif len(new_password) < 8:
            st.error(
                "The new password must be at least 8 characters."
            )

        elif len(new_password.encode()) > 72:
            st.error(
                "The new password is too long."
            )

        elif current_password == new_password:
            st.error(
                "The new password must differ from "
                "your current password."
            )

        elif new_password != confirm_password:
            st.error(
                "The new passwords do not match."
            )

        else:
            success, message = change_password(
                conn,
                st.session_state.user["user_id"],
                current_password,
                new_password
            )

            if success:
                end_session(
                    "Password changed successfully. "
                    "Please sign in with your new password.",
                    notice_type="success"
                )

            else:
                st.error(message)


# ---------- Mandatory password change screen ----------

def required_password_page():
    left, right = st.columns(
        [1.15, 1],
        gap="large"
    )

    with left:
        login_art(
            headline=(
                'Your account. '
                '<span>Your security.</span>'
            ),
            sub=(
                "Set a personal password to protect "
                "your account and confidential lending information."
            )
        )

    with right:
        st.markdown(
            "<div style='height:25px'></div>",
            unsafe_allow_html=True
        )

        st.markdown("## Secure your account")

        password_change_form(required=True)

        if st.button(
            "Sign out",
            key="required_password_signout",
            use_container_width=True
        ):
            end_session()


# ---------- Voluntary password change screen ----------

def voluntary_password_page():
    page_header(
        "Change Password",
        "Manage your account security."
    )

    left, right = st.columns([1.2, 1])

    with left:
        password_change_form(required=False)

    with right:
        with st.container(border=True):
            st.markdown("### Keep your account secure")

            st.write(
                "Choose a password that is difficult "
                "for other people to guess."
            )

            st.markdown(
                "- Do not share your password with anyone.\n"
                "- Avoid using personal information.\n"
                "- Use a unique password for this system.\n"
                "- Change your password if you suspect "
                "unauthorized access."
            )

            st.info(
                "After changing your password, you will "
                "be signed out and asked to sign in again."
            )


# ---------- Sidebar navigation ----------

def sidebar_nav(items):
    user = st.session_state.user

    if user["role"] == "loan_officer":
        role_label = "Loan Officer"

    else:
        access_level = user.get(
            "access_level", "Limited access"
        )

        role_label = (
            f"Administrator | {access_level}"
        )

    sidebar_brand(role_label)

    if "pending_nav" in st.session_state:
        pending = st.session_state.pop("pending_nav")

        if pending in items:
            st.session_state["nav"] = pending

    if (
        "nav" in st.session_state
        and st.session_state["nav"] not in items
    ):
        st.session_state["nav"] = items[0]

    choice = st.sidebar.radio(
        "Navigate",
        items,
        key="nav",
        label_visibility="collapsed"
    )

    st.sidebar.markdown(
        "<div style='height:24px'></div>",
        unsafe_allow_html=True
    )

    if st.sidebar.button("Sign out"):
        end_session()

    return choice


# ---------- Application routing ----------

if st.session_state.user is None:

    login_page()


elif st.session_state.user["must_change_password"]:

    required_password_page()


elif st.session_state.user["role"] == "loan_officer":

    choice = sidebar_nav([
        "Submit Application",
        "My Applications",
        "Change Password"
    ])

    if choice == "Submit Application":

        submit_application_screen(
            conn,
            sector_list,
            NAICS_LABELS
        )

    elif choice == "My Applications":

        my_applications_screen(
            conn,
            NAICS_LABELS
        )

    elif choice == "Change Password":

        voluntary_password_page()


elif st.session_state.user["role"] == "admin":

    access_level = st.session_state.user.get(
        "access_level"
    )

    if access_level == "Full access":

        choice = sidebar_nav([
            "Manage Users",
            "System Performance",
            "Change Password"
        ])

    else:

        choice = sidebar_nav([
            "User Directory",
            "System Performance",
            "Change Password"
        ])

    if choice == "Manage Users":

        manage_users_screen(conn)

    elif choice == "User Directory":

        user_directory_screen(conn)

    elif choice == "System Performance":

        system_performance_screen(conn)

    elif choice == "Change Password":

        voluntary_password_page()


else:

    end_session(
        "Your account has an invalid role. "
        "Contact your administrator."
    )