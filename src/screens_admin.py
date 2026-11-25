import os
import re
import sqlite3
import json
import pandas as pd
import streamlit as st

from database import (
    list_users,
    add_user,
    set_user_active,
    reset_password,
    update_user_detail,
    get_admin_id,
    get_admin_access_level,
    has_full_admin_access,
    usage_summary,
    band_counts,
    applications_per_day
)

from metrics import scoring_stats
from report_text import BAND_INFO

from theme import (
    page_header,
    kpi_cards,
    band_donut,
    per_day_chart,
    model_comparison_chart,
    BRAND,
    LOW,
    MODERATE,
    ELEVATED,
    INK
)


ROLE_LABELS = {
    "loan_officer": "Loan Officer",
    "admin": "Administrator"
}

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,50}$")


# ---------- Branches and access levels ----------

_BRANCH_TOWNS = [
    ("CBD", "Nairobi"),
    ("Westlands", "Nairobi"),
    ("Kilimani", "Nairobi"),
    ("Karen", "Nairobi"),
    ("Eastleigh", "Nairobi"),
    ("Thika", "Kiambu"),
    ("Ruiru", "Kiambu"),
    ("Kitengela", "Kajiado"),
    ("Machakos Town", "Machakos"),
    ("Nakuru Town", "Nakuru"),
    ("Naivasha", "Nakuru"),
    ("Eldoret", "Uasin Gishu"),
    ("Kisumu Central", "Kisumu"),
    ("Kakamega Town", "Kakamega"),
    ("Kisii Town", "Kisii"),
    ("Mombasa Island", "Mombasa"),
    ("Nyali", "Mombasa"),
    ("Malindi", "Kilifi"),
    ("Nyeri Town", "Nyeri"),
    ("Nanyuki", "Laikipia"),
    ("Meru Town", "Meru"),
    ("Embu Town", "Embu"),
    ("Kericho Town", "Kericho"),
    ("Garissa Town", "Garissa"),
]

BRANCHES = [
    f"{t}, {c} County"
    for t, c in _BRANCH_TOWNS
]

ACCESS_LEVELS = [
    "Full access",
    "Limited access"
]


# ---------- Shared helper functions ----------

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
        return "The password is too long. Please use a shorter password."

    return None


def _options_with(current, options):
    """Keeps previously saved values selectable."""

    return (
        options
        if not current or current in options
        else [current] + options
    )


def _admin_access(conn):
    """Returns the current administrator's access level."""

    user = st.session_state.get("user")

    if not user or user.get("role") != "admin":
        return None

    return get_admin_access_level(
        conn,
        user["user_id"]
    )


def _access_level_guide():
    """Explains the two administrator access levels."""

    with st.expander("Understanding administrator access levels"):

        st.markdown("**Full access**")

        st.write(
            "Can view system performance, create accounts, "
            "reset other users' passwords, activate or deactivate "
            "accounts and update user details."
        )

        st.markdown("**Limited access**")

        st.write(
            "Can view the user directory and system performance "
            "but cannot create accounts, reset other users' "
            "passwords or modify account details."
        )

        st.caption(
            "Both administrator types can change their own passwords."
        )


def _user_statistics(users):
    """Displays account statistics."""

    kpi_cards([
        (
            "Total accounts",
            len(users),
            INK
        ),
        (
            "Active",
            sum(1 for u in users if u["is_active"]),
            LOW
        ),
        (
            "Loan officers",
            sum(
                1 for u in users
                if u["role"] == "loan_officer"
            ),
            BRAND
        ),
        (
            "Deactivated",
            sum(1 for u in users if not u["is_active"]),
            ELEVATED
        )
    ])


def _user_table(users):
    """Displays a searchable, read-only table of registered users."""

    st.subheader("Registered users")

    c1, c2, c3 = st.columns([2, 1, 1])

    search = c1.text_input(
        "Search users",
        placeholder="Search by username or branch"
    ).strip().lower()

    role_filter = c2.selectbox(
        "Filter by role",
        ["All roles", "Loan Officer", "Administrator"]
    )

    status_filter = c3.selectbox(
        "Filter by status",
        ["All statuses", "Active", "Deactivated"]
    )

    filtered = []

    for user in users:

        role = ROLE_LABELS.get(
            user["role"],
            user["role"]
        )

        status = (
            "Active"
            if user["is_active"]
            else "Deactivated"
        )

        search_text = " ".join([
            user["username"],
            user["detail"] or "",
            user["managed_by"] or "",
            role
        ]).lower()

        if search and search not in search_text:
            continue

        if role_filter != "All roles" and role != role_filter:
            continue

        if status_filter != "All statuses" and status != status_filter:
            continue

        filtered.append({
            "ID": user["user_id"],
            "Username": user["username"],
            "Role": role,
            "Branch / access level": user["detail"] or "",
            "Managed by": user["managed_by"] or "",
            "Applications": (
                "-"
                if user["applications"] is None
                else str(user["applications"])
            ),
            "Status": (
                "🟢 Active"
                if user["is_active"]
                else "🔴 Deactivated"
            )
        })

    st.caption(
        f"Showing {len(filtered)} of {len(users)} accounts"
    )

    if not filtered:
        st.info("No accounts match your search or filters.")
        return

    st.dataframe(
        pd.DataFrame(filtered),
        hide_index=True,
        use_container_width=True
    )


# ---------- Read-only user directory ----------

def user_directory_screen(conn):
    """Allows administrators to view registered users."""

    access_level = _admin_access(conn)

    if access_level not in ACCESS_LEVELS:
        st.error(
            "You do not have permission to access the user directory."
        )
        return

    page_header(
        "User Directory",
        "View registered accounts, roles and account statuses."
    )

    st.info(
        "Read-only access: You can view registered users "
        "but cannot modify accounts or reset passwords "
        "from this page."
    )

    users = list_users(conn)

    _user_statistics(users)
    _user_table(users)
    _access_level_guide()


# ---------- Full-access user management ----------

def manage_users_screen(conn):
    """Allows full-access administrators to manage user accounts."""

    me = st.session_state.get("user")

    if not me or not has_full_admin_access(
        conn,
        me["user_id"]
    ):
        st.error(
            "Full administrator access is required "
            "to manage user accounts."
        )
        return

    page_header(
        "Manage Users",
        "Manage system accounts, branches and permissions."
    )

    _show_flash()

    my_admin_id = get_admin_id(
        conn,
        me["user_id"]
    )

    users = list_users(conn)

    _user_statistics(users)
    _user_table(users)
    _access_level_guide()

    st.divider()

    # ---------- Add a user ----------

    st.subheader("Add a user")

    st.caption(
        "Create an account and assign a temporary password. "
        "The user must set a personal password when they first sign in."
    )

    role_label = st.radio(
        "Role",
        ["Loan Officer", "Administrator"],
        horizontal=True,
        key="new_role"
    )

    is_officer = role_label == "Loan Officer"

    with st.form(
        "add_user_form",
        clear_on_submit=True
    ):

        c1, c2, c3 = st.columns(3)

        username = c1.text_input(
            "Username",
            placeholder="e.g. j.kimani"
        )

        password = c2.text_input(
            "Temporary password",
            type="password",
            help="Must contain at least 8 characters."
        )

        detail = c3.selectbox(
            "Branch" if is_officer else "Access level",
            BRANCHES if is_officer else ACCESS_LEVELS,
            index=0 if is_officer else 1
        )

        submitted = st.form_submit_button(
            "Create account"
        )

    if submitted:

        username = username.strip()
        password_error = _password_problem(password)

        if not USERNAME_RE.fullmatch(username):

            st.error(
                "Username must be 3 to 50 characters and "
                "contain only letters, digits, dots, "
                "dashes or underscores."
            )

        elif password_error:

            st.error(password_error)

        else:

            try:

                add_user(
                    conn,
                    username,
                    password,
                    "loan_officer" if is_officer else "admin",
                    detail,
                    my_admin_id,
                    actor_user_id=me["user_id"]
                )

            except sqlite3.IntegrityError:

                st.error(
                    f"The username '{username}' is already taken "
                    "or the account could not be created."
                )

            except (PermissionError, ValueError) as exc:

                st.error(str(exc))

            except sqlite3.Error:

                st.error(
                    "The account could not be created. "
                    "Please try again."
                )

            else:

                _flash(
                    f"Account created for {username} ({role_label}). "
                    "The user must change their temporary password "
                    "when they first sign in."
                )

                st.rerun()

    st.divider()

    # ---------- Edit a user ----------

    st.subheader("Edit a user")

    st.caption(
        "Select an account to manage its password, "
        "branch, access level or account status."
    )

    if not users:
        st.info("No registered accounts are available.")
        return

    by_id = {
        u["user_id"]: u
        for u in users
    }

    uid = st.selectbox(
        "Select user",
        list(by_id),
        key="edit_user",
        format_func=lambda i: (
            f"{by_id[i]['username']} "
            f"({ROLE_LABELS.get(by_id[i]['role'], by_id[i]['role'])})"
        )
    )

    user = by_id[uid]

    is_self = uid == me["user_id"]
    is_officer = user["role"] == "loan_officer"

    with st.container(border=True):

        c1, c2, c3 = st.columns(3)

        with c1:
            st.caption("Username")
            st.markdown(f"**{user['username']}**")

        with c2:
            st.caption("Role")
            st.markdown(
                f"**{ROLE_LABELS.get(user['role'], user['role'])}**"
            )

        with c3:
            st.caption("Account status")

            if user["is_active"]:
                st.markdown("🟢 **Active**")
            else:
                st.markdown("🔴 **Deactivated**")

    if is_self:

        st.info(
            "This is your own account. Use Change Password "
            "in the sidebar to update your password. "
            "You cannot deactivate your own account "
            "or change your own access level."
        )

    left, right = st.columns(2)

    # ---------- Reset password ----------

    with left:

        with st.container(border=True):

            st.markdown("### Reset password")

            st.caption(
                "Assign a new temporary password. "
                "The user's previous sessions will be invalidated "
                "and a password change will be required."
            )

            if is_self:

                st.info(
                    "Use Change Password to update your own password."
                )

            else:

                with st.form(
                    f"reset_password_form_{uid}",
                    clear_on_submit=True
                ):

                    new_pw = st.text_input(
                        "New temporary password",
                        type="password"
                    )

                    reset_submitted = st.form_submit_button(
                        "Reset password"
                    )

                if reset_submitted:

                    password_error = _password_problem(new_pw)

                    if password_error:

                        st.error(password_error)

                    else:

                        try:

                            reset_password(
                                conn,
                                uid,
                                new_pw,
                                actor_user_id=me["user_id"]
                            )

                        except (PermissionError, ValueError) as exc:

                            st.error(str(exc))

                        except sqlite3.Error:

                            st.error(
                                "The password could not be reset. "
                                "Please try again."
                            )

                        else:

                            _flash(
                                f"Password reset for {user['username']}. "
                                "A password change is required "
                                "at their next login."
                            )

                            st.rerun()

    # ---------- Update user details ----------

    with right:

        with st.container(border=True):

            st.markdown("### Account details")

            label = (
                "Branch"
                if is_officer
                else "Access level"
            )

            st.caption(
                "Update the loan officer's branch."
                if is_officer
                else "Update the administrator's permissions."
            )

            if is_self:

                st.text_input(
                    label,
                    value=user["detail"] or "",
                    disabled=True,
                    key=f"own_detail_{uid}"
                )

            else:

                opts = _options_with(
                    user["detail"],
                    BRANCHES if is_officer else ACCESS_LEVELS
                )

                idx = (
                    opts.index(user["detail"])
                    if user["detail"] in opts
                    else 0
                )

                with st.form(
                    f"update_details_form_{uid}"
                ):

                    new_detail = st.selectbox(
                        label,
                        opts,
                        index=idx
                    )

                    details_submitted = st.form_submit_button(
                        "Save changes"
                    )

                if details_submitted:

                    if new_detail == user["detail"]:

                        st.info(
                            "No changes have been made."
                        )

                    else:

                        try:

                            update_user_detail(
                                conn,
                                uid,
                                new_detail,
                                actor_user_id=me["user_id"]
                            )

                        except (PermissionError, ValueError) as exc:

                            st.error(str(exc))

                        except sqlite3.Error:

                            st.error(
                                "The account details could not "
                                "be updated. Please try again."
                            )

                        else:

                            _flash(
                                f"{label} updated for "
                                f"{user['username']}."
                            )

                            st.rerun()

    # ---------- Account activation and deactivation ----------

    with st.container(border=True):

        st.markdown("### Account status")

        st.caption(
            "Deactivating an account prevents the user from "
            "signing in and invalidates their existing sessions. "
            "Their historical records are preserved."
        )

        if is_self:

            st.info(
                "You cannot deactivate your own account."
            )

        else:

            currently_active = bool(
                user["is_active"]
            )

            action = (
                "Deactivate"
                if currently_active
                else "Activate"
            )

            if currently_active:

                st.warning(
                    f"Deactivating {user['username']} will "
                    "prevent them from accessing the system."
                )

            else:

                st.info(
                    f"Activating {user['username']} will "
                    "restore their ability to sign in."
                )

            with st.form(
                f"account_status_form_{uid}_{int(currently_active)}",
                clear_on_submit=True
            ):

                confirmed = st.checkbox(
                    f"I confirm that I want to "
                    f"{action.lower()} this account."
                )

                status_submitted = st.form_submit_button(
                    f"{action} account"
                )

            if status_submitted:

                if not confirmed:

                    st.error(
                        "Please confirm the action before proceeding."
                    )

                else:

                    try:

                        set_user_active(
                            conn,
                            uid,
                            not currently_active,
                            actor_user_id=me["user_id"]
                        )

                    except (PermissionError, ValueError) as exc:

                        st.error(str(exc))

                    except sqlite3.Error:

                        st.error(
                            "The account status could not "
                            "be updated. Please try again."
                        )

                    else:

                        _flash(
                            f"{user['username']} has been "
                            f"{action.lower()}d successfully."
                        )

                        st.rerun()


# ---------- System performance ----------

def system_performance_screen(conn):

    page_header(
        "System Performance",
        "How the system is being used"
    )

    s = usage_summary(conn)
    decided = s["approved"] + s["rejected"]

    kpi_cards([
        ("Applications today", s["today"], BRAND),
        ("Last 7 days", s["last7"], BRAND),
        ("All time", s["total"], INK),
        ("Pending decisions", s["pending"], MODERATE)
    ])

    kpi_cards([
        ("Approved", s["approved"], LOW),
        ("Rejected", s["rejected"], ELEVATED),
        (
            "Approval rate",
            f"{s['approved'] / decided:.0%}" if decided else "n/a",
            INK
        ),
        (
            "Active accounts",
            f"{s['users_active']} of {s['users_total']}",
            INK
        )
    ])

    left, right = st.columns([1.6, 1])

    with left:

        st.subheader("Applications per day")
        per_day_chart(
            applications_per_day(conn, 14)
        )

    with right:

        st.subheader("Risk band mix")
        counts = band_counts(conn)
        band_donut(counts)

    total = sum(counts.values())

    st.dataframe(
        pd.DataFrame([
            {
                "Band": band,
                "Applications": counts.get(band, 0),
                "Share so far": (
                    f"{counts.get(band, 0) / total:.0%}"
                    if total else "n/a"
                ),
                "Share in the test data": (
                    f"{BAND_INFO[band]['share']:.0%}"
                )
            }
            for band in ["Low", "Moderate", "Elevated"]
        ]),
        hide_index=True,
        use_container_width=True
    )

    st.subheader("Scoring speed")

    stats = scoring_stats()

    if stats is None:

        st.info("Nothing scored yet in this session.")

    else:

        kpi_cards([
            (
                "Average time",
                f"{stats['avg']:.0f} ms",
                BRAND
            ),
            (
                "Slowest",
                f"{stats['max']:.0f} ms",
                MODERATE
            ),
            (
                "Applications scored",
                stats["count"],
                INK
            )
        ])

    st.subheader("Model quality")

    path = "models/model_results.csv"

    if os.path.exists(path):

        rf_row = pd.read_csv(path).query(
            "Model == 'Random Forest'"
        )

        if not rf_row.empty:

            r = rf_row.iloc[0]

            kpi_cards([
                (
                    "ROC-AUC",
                    f"{r['ROC-AUC']:.3f}",
                    BRAND
                ),
                (
                    "PR-AUC",
                    f"{r['PR-AUC']:.3f}",
                    BRAND
                ),
                (
                    "Precision",
                    f"{r['Precision']:.3f}",
                    INK
                ),
                (
                    "Recall",
                    f"{r['Recall']:.3f}",
                    INK
                )
            ])

    else:

        st.info("Model results file not found.")

    st.subheader("Model comparison")

    model_comparison_chart()