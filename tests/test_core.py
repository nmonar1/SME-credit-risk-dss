"""Unit tests for the SME Credit Risk DSS.

"""
import json
import os
import sqlite3
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)  # the app loads models/ with relative paths

import database as db
from report_text import pct_text, pct_short

MODELS_PRESENT = os.path.exists("models/random_forest_model.pkl") and os.path.exists("models/isotonic_calibrator.pkl")
needs_models = pytest.mark.skipif(not MODELS_PRESENT, reason="trained models not found")


# ---------------------------------------------------------------- helpers
@pytest.fixture
def conn(tmp_path):
    c = db.init_db(str(tmp_path / "test.db"))
    db.migrate_db(c)
    return c

@pytest.fixture
def admin_user(conn):
    user_id = db.create_user(
        conn, "test_admin", "AdminPass123", "admin"
    )

    cur = conn.execute(
        """
        INSERT INTO system_administrators (user_id, access_level)
        VALUES (?, ?)
        """,
        (user_id, "Full access")
    )

    conn.commit()

    return {
        "user_id": user_id,
        "admin_id": cur.lastrowid
    }

def make_officer(conn, name="officer1"):
    user_id = db.create_user(
        conn, name, "password123", "loan_officer"
    )

    cur = conn.execute(
        """
        INSERT INTO loan_officers (user_id, branch_office)
        VALUES (?, ?)
        """,
        (user_id, "Westlands, Nairobi County")
    )

    conn.commit()

    return user_id, cur.lastrowid


APP = {"business_name": "Mama Njeri Supplies", "industry_type": "44", "num_employees": 5, "business_age": 3,
       "loan_amount": 50000.0, "loan_term": 60, "application_date": "2026-11-01"}
RESULT = {"risk_score": 0.21, "risk_classification": "Low", "plain_language_summary": "summary",
          "top_features": json.dumps([{"feature": "Loan amount", "value": 0.05}])}


# ---------------------------------------------------------------- U01 to U05: login and accounts
def test_U01_password_is_stored_hashed(conn):
    db.create_user(conn, "alice", "MySecret99", "loan_officer")
    stored = conn.execute("SELECT password_hash FROM users WHERE username='alice'").fetchone()[0]
    assert stored != "MySecret99"
    assert stored.startswith("$2")          # bcrypt format


def test_U02_same_password_gives_different_hashes(conn):
    db.create_user(conn, "a", "SamePass123", "loan_officer")
    db.create_user(conn, "b", "SamePass123", "loan_officer")
    hashes = [r[0] for r in conn.execute("SELECT password_hash FROM users ORDER BY user_id")]
    assert hashes[0] != hashes[1]           # salt makes them different


def test_U03_login_correct_wrong_and_unknown(conn):
    db.create_user(conn, "alice", "MySecret99", "loan_officer")
    assert db.authenticate(conn, "alice", "MySecret99")["role"] == "loan_officer"
    assert db.authenticate(conn, "alice", "WrongPass") is None
    assert db.authenticate(conn, "nobody", "MySecret99") is None


def test_U04_deactivated_account_is_flagged_inactive(conn, admin_user):
    uid = db.create_user(
        conn, "bob", "MySecret99", "loan_officer"
    )

    assert db.authenticate(conn, "bob", "MySecret99")["active"] is True

    db.set_user_active(
        conn, uid, False,
        actor_user_id=admin_user["user_id"]
    )

    assert db.authenticate(conn, "bob", "MySecret99")["active"] is False
    assert db.is_user_active(conn, uid) is False

    db.set_user_active(
        conn, uid, True,
        actor_user_id=admin_user["user_id"]
    )

    assert db.is_user_active(conn, uid) is True


def test_U05_password_longer_than_72_bytes_is_rejected(conn):
    db.create_user(conn, "carol", "MySecret99", "loan_officer")
    assert db.authenticate(conn, "carol", "x" * 100) is None


def test_U06_duplicate_username_is_rejected_and_nothing_is_left_behind(conn, admin_user):
    db.add_user(
        conn, "dave", "password123", "loan_officer",
        "CBD, Nairobi County",
        admin_user["admin_id"],
        actor_user_id=admin_user["user_id"]
    )

    with pytest.raises(sqlite3.IntegrityError):
        db.add_user(
            conn, "dave", "password123", "loan_officer",
            "CBD, Nairobi County",
            admin_user["admin_id"],
            actor_user_id=admin_user["user_id"]
        )

    assert conn.execute(
        "SELECT COUNT(*) FROM users WHERE username='dave'"
    ).fetchone()[0] == 1

    assert conn.execute(
        "SELECT COUNT(*) FROM loan_officers"
    ).fetchone()[0] == 1


def test_U07_reset_password_changes_login(conn, admin_user):
    uid = db.create_user(
        conn, "eve", "OldPass123", "loan_officer"
    )

    db.reset_password(
        conn, uid, "NewPass456",
        actor_user_id=admin_user["user_id"]
    )

    assert db.authenticate(conn, "eve", "OldPass123") is None

    user = db.authenticate(conn, "eve", "NewPass456")

    assert user is not None
    assert user["must_change_password"] is True

# ---------------------------------------------------------------- U08 to U12: applications and decisions
def test_U08_new_application_starts_pending_without_assessment(conn):
    _, oid = make_officer(conn)
    db.save_application(conn, oid, APP)
    row = db.list_applications(conn, oid)[0]
    assert row["application_status"] == "Pending"
    assert row["risk_score"] is None


def test_U09_assessment_and_explanation_are_saved_and_joined(conn):
    _, oid = make_officer(conn)
    app_id = db.save_application(conn, oid, APP)
    db.save_risk_assessment(conn, app_id, RESULT)
    row = db.get_application(conn, app_id, oid)
    assert row["risk_classification"] == "Low"
    assert abs(row["risk_score"] - 0.21) < 1e-9
    assert row["plain_language_summary"] == "summary"


def test_U10_decision_updates_status_and_only_one_decision_is_allowed(conn):
    _, oid = make_officer(conn)
    app_id = db.save_application(conn, oid, APP)
    db.save_decision(conn, app_id, oid, "Rejected", "Loan amount too high")
    row = db.get_application(conn, app_id, oid)
    assert row["application_status"] == "Rejected"
    assert row["decision_reason"] == "Loan amount too high"
    with pytest.raises(sqlite3.IntegrityError):
        db.save_decision(conn, app_id, oid, "Approved")


def test_U11_officer_cannot_open_another_officers_application(conn):
    _, oid1 = make_officer(conn, "officer1")
    _, oid2 = make_officer(conn, "officer2")
    app_id = db.save_application(conn, oid1, APP)
    assert db.get_application(conn, app_id, oid1) is not None
    assert db.get_application(conn, app_id, oid2) is None
    assert db.list_applications(conn, oid2) == []


def test_U12_foreign_keys_are_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        db.save_application(conn, 999, APP)     # officer 999 does not exist


# ---------------------------------------------------------------- U13 to U14: admin summaries
def test_U13_usage_summary_and_band_counts(conn):
    _, oid = make_officer(conn)
    a1 = db.save_application(conn, oid, APP)
    a2 = db.save_application(conn, oid, APP)
    db.save_risk_assessment(conn, a1, RESULT)
    db.save_risk_assessment(conn, a2, {**RESULT, "risk_classification": "Elevated"})
    db.save_decision(conn, a1, oid, "Approved")
    s = db.usage_summary(conn)
    assert s["total"] == 2 and s["approved"] == 1 and s["pending"] == 1
    assert db.band_counts(conn) == {"Low": 1, "Elevated": 1}


def test_U14_applications_per_day_returns_one_row_per_day(conn):
    rows = db.applications_per_day(conn, 14)
    assert len(rows) == 14 and all(count == 0 for _, count in rows)


# ---------------------------------------------------------------- U15: wording helpers
def test_U15_percentage_wording_never_shows_zero_percent():
    assert pct_text(0.0) == "less than 1%"
    assert pct_text(0.2) == "20%"
    assert pct_short(0.005) == "<1%"
    assert pct_short(0.203) == "20.3%"


# ---------------------------------------------------------------- model and explanation tests
@pytest.fixture(scope="module")
def se():
    import shap_explainer
    return shap_explainer


@needs_models
def test_U16_risk_bands_follow_the_saved_cut_offs(se):
    low, high = se.THRESHOLDS["low_max"], se.THRESHOLDS["high_min"]
    assert se.classify_risk(low - 0.01) == "Low"
    assert se.classify_risk(low) == "Moderate"
    assert se.classify_risk(high - 0.01) == "Moderate"
    assert se.classify_risk(high) == "Elevated"


@needs_models
def test_U17_shap_share_is_turned_into_plain_words(se):
    assert se._strength(0.60) == "the main driver"
    assert se._strength(0.30) == "a moderate influence"
    assert se._strength(0.10) == "a small influence"
    assert se._strength(0.01) == "almost no effect"


@needs_models
def test_U18_model_uses_only_the_four_agreed_features_and_not_term():
    features = joblib.load("models/feature_columns.pkl")
    assert features == ["NoEmp", "GrAppv", "NewExist", "NAICS_Sector"]
    assert "Term" not in features           # the leaking column must stay out


@needs_models
def test_U19_calibrator_keeps_the_ranking(se):
    values = se.iso.predict(np.linspace(0, 1, 200))
    assert np.all(np.diff(values) >= 0)
    assert values.min() >= 0 and values.max() <= 1


@needs_models
def test_U20_full_explanation_output_is_complete(se):
    row = pd.DataFrame([{"NoEmp": 5, "GrAppv": 50000.0, "NewExist": 2.0, "NAICS_Sector": 0}])
    result = se.explain_application(row)
    assert 0 <= result["risk_score"] <= 1
    assert result["risk_classification"] in ("Low", "Moderate", "Elevated")
    features = json.loads(result["top_features"])
    assert len(features) == 4
    assert "decision support, not a decision" in result["plain_language_summary"]

    # ---------------------------------------------------------------- U21 to U32: enhanced security

def test_U21_new_account_requires_password_change(conn, admin_user):
    db.add_user(
        conn, "new_officer", "TempPass123", "loan_officer",
        "CBD, Nairobi County",
        admin_user["admin_id"],
        actor_user_id=admin_user["user_id"]
    )

    user = db.authenticate(conn, "new_officer", "TempPass123")

    assert user is not None
    assert user["must_change_password"] is True


def test_U22_successful_password_change(conn, admin_user):
    uid = db.add_user(
        conn, "new_officer", "TempPass123", "loan_officer",
        "CBD, Nairobi County",
        admin_user["admin_id"],
        actor_user_id=admin_user["user_id"]
    )

    success, message = db.change_password(
        conn, uid, "TempPass123", "PersonalPass456"
    )

    assert success is True
    assert db.authenticate(conn, "new_officer", "TempPass123") is None

    user = db.authenticate(conn, "new_officer", "PersonalPass456")

    assert user is not None
    assert user["must_change_password"] is False


def test_U23_incorrect_current_password_is_rejected(conn):
    uid = db.create_user(
        conn, "officer", "OriginalPass123", "loan_officer"
    )

    success, message = db.change_password(
        conn, uid, "WrongPassword", "NewPassword123"
    )

    assert success is False
    assert db.authenticate(conn, "officer", "OriginalPass123") is not None


def test_U24_weak_or_reused_password_is_rejected(conn):
    uid = db.create_user(
        conn, "officer", "OriginalPass123", "loan_officer"
    )

    for new_password in ("abc", "OriginalPass123", "x" * 73):
        success, message = db.change_password(
            conn, uid, "OriginalPass123", new_password
        )

        assert success is False

    assert db.authenticate(conn, "officer", "OriginalPass123") is not None

@pytest.fixture
def limited_admin(conn, admin_user):
    uid = db.add_user(
        conn, "limited_admin", "TempAdmin123", "admin",
        "Limited access",
        admin_user["admin_id"],
        actor_user_id=admin_user["user_id"]
    )

    success, message = db.change_password(
        conn, uid, "TempAdmin123", "PersonalAdmin456"
    )

    assert success is True

    return uid


def test_U25_limited_admin_cannot_create_accounts(conn, limited_admin):
    with pytest.raises(PermissionError):
        db.add_user(
            conn, "unauthorized_user", "Password123",
            "loan_officer", "CBD, Nairobi County",
            db.get_admin_id(conn, limited_admin),
            actor_user_id=limited_admin
        )

    assert conn.execute(
        "SELECT COUNT(*) FROM users WHERE username='unauthorized_user'"
    ).fetchone()[0] == 0


def test_U26_limited_admin_cannot_reset_passwords(conn, limited_admin):
    uid, _ = make_officer(conn)

    with pytest.raises(PermissionError):
        db.reset_password(
            conn, uid, "NewPassword123",
            actor_user_id=limited_admin
        )

    assert db.authenticate(conn, "officer1", "password123") is not None


def test_U27_limited_admin_cannot_deactivate_users(conn, limited_admin):
    uid, _ = make_officer(conn)

    with pytest.raises(PermissionError):
        db.set_user_active(
            conn, uid, False,
            actor_user_id=limited_admin
        )

    assert db.is_user_active(conn, uid) is True


def test_U28_limited_admin_cannot_modify_access_level(conn, limited_admin):
    with pytest.raises(PermissionError):
        db.update_user_detail(
            conn, limited_admin, "Full access",
            actor_user_id=limited_admin
        )

    assert db.get_admin_access_level(conn, limited_admin) == "Limited access"

def test_U29_admin_cannot_deactivate_own_account(conn, admin_user):
    uid = admin_user["user_id"]

    with pytest.raises(PermissionError):
        db.set_user_active(
            conn, uid, False,
            actor_user_id=uid
        )

    assert db.is_user_active(conn, uid) is True


def test_U30_admin_cannot_downgrade_own_access(conn, admin_user):
    uid = admin_user["user_id"]

    with pytest.raises(PermissionError):
        db.update_user_detail(
            conn, uid, "Limited access",
            actor_user_id=uid
        )

    assert db.get_admin_access_level(conn, uid) == "Full access"


def test_U31_loan_officer_cannot_manage_users(conn):
    uid, _ = make_officer(conn)

    with pytest.raises(PermissionError):
        db.set_user_active(
            conn, uid, False,
            actor_user_id=uid
        )

    assert db.is_user_active(conn, uid) is True


def test_U32_temporary_password_blocks_admin_actions(conn, admin_user):
    uid = db.add_user(
        conn, "new_admin", "TempAdmin123", "admin",
        "Full access",
        admin_user["admin_id"],
        actor_user_id=admin_user["user_id"]
    )

    assert db.has_full_admin_access(conn, uid) is False

    with pytest.raises(PermissionError):
        db.add_user(
            conn, "blocked_user", "Password123",
            "loan_officer", "CBD, Nairobi County",
            db.get_admin_id(conn, uid),
            actor_user_id=uid
        )

    success, message = db.change_password(
        conn, uid, "TempAdmin123", "PersonalAdmin456"
    )

    assert success is True
    assert db.has_full_admin_access(conn, uid) is True


# ---------- U33 to U37: Session security ----------

def test_U33_password_reset_invalidates_session(conn, admin_user):
    uid, _ = make_officer(conn)

    old_session = db.authenticate(
        conn, "officer1", "password123"
    )

    db.reset_password(
        conn, uid, "TemporaryPass123",
        actor_user_id=admin_user["user_id"]
    )

    status = db.get_session_status(conn, uid)

    assert status["session_version"] == old_session["session_version"] + 1
    assert status["must_change_password"] is True

    assert db.authenticate(
        conn, "officer1", "password123"
    ) is None


def test_U34_password_change_invalidates_session(conn):
    uid, _ = make_officer(conn)

    old_session = db.authenticate(
        conn, "officer1", "password123"
    )

    success, message = db.change_password(
        conn, uid, "password123", "PersonalPass456"
    )

    assert success is True

    status = db.get_session_status(conn, uid)

    assert status["session_version"] == old_session["session_version"] + 1
    assert status["must_change_password"] is False

    new_session = db.authenticate(
        conn, "officer1", "PersonalPass456"
    )

    assert new_session is not None
    assert new_session["session_version"] == status["session_version"]


def test_U35_deactivation_and_reactivation_invalidate_session(
    conn, admin_user
):
    uid, _ = make_officer(conn)

    old_session = db.authenticate(
        conn, "officer1", "password123"
    )

    db.set_user_active(
        conn, uid, False,
        actor_user_id=admin_user["user_id"]
    )

    status = db.get_session_status(conn, uid)

    assert status["active"] is False
    assert status["session_version"] == old_session["session_version"] + 1

    db.set_user_active(
        conn, uid, True,
        actor_user_id=admin_user["user_id"]
    )

    status = db.get_session_status(conn, uid)

    assert status["active"] is True
    assert status["session_version"] == old_session["session_version"] + 2


def test_U36_access_level_change_invalidates_session(
    conn, admin_user, limited_admin
):
    old_status = db.get_session_status(conn, limited_admin)

    db.update_user_detail(
        conn, limited_admin, "Full access",
        actor_user_id=admin_user["user_id"]
    )

    new_status = db.get_session_status(conn, limited_admin)

    assert new_status["session_version"] == old_status["session_version"] + 1
    assert db.get_admin_access_level(conn, limited_admin) == "Full access"
    assert db.has_full_admin_access(conn, limited_admin) is True


def test_U37_failed_password_change_preserves_session(conn):
    uid, _ = make_officer(conn)

    old_status = db.get_session_status(conn, uid)

    success, message = db.change_password(
        conn, uid, "IncorrectPassword", "NewPassword123"
    )

    assert success is False

    new_status = db.get_session_status(conn, uid)

    assert new_status["session_version"] == old_status["session_version"]

    assert db.authenticate(
        conn, "officer1", "password123"
    ) is not None