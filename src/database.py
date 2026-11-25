import sqlite3
import bcrypt

DB_PATH = "database/credit_risk.db"


def init_db(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username VARCHAR(100) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        role VARCHAR(50) NOT NULL,
        managed_by_admin_id INTEGER,
        is_active INTEGER NOT NULL DEFAULT 1,
        must_change_password INTEGER NOT NULL DEFAULT 0,
        session_version INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (managed_by_admin_id) REFERENCES system_administrators(admin_id)
    );
    CREATE TABLE IF NOT EXISTS loan_officers (
        officer_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        branch_office VARCHAR(100),
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    );
    CREATE TABLE IF NOT EXISTS system_administrators (
        admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        access_level VARCHAR(50),
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    );
    CREATE TABLE IF NOT EXISTS loan_applications (
        application_id INTEGER PRIMARY KEY AUTOINCREMENT,
        officer_id INTEGER NOT NULL,
        business_name VARCHAR(150),
        industry_type VARCHAR(100),
        num_employees INTEGER,
        business_age INTEGER,
        loan_amount DECIMAL(12,2),
        loan_term INTEGER,
        application_date DATE,
        application_status VARCHAR(50),
        FOREIGN KEY (officer_id) REFERENCES loan_officers(officer_id)
    );
    CREATE TABLE IF NOT EXISTS decisions (
        decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER UNIQUE NOT NULL,
        officer_id INTEGER NOT NULL,
        decision VARCHAR(20),
        decision_reason VARCHAR(255),
        FOREIGN KEY (application_id) REFERENCES loan_applications(application_id),
        FOREIGN KEY (officer_id) REFERENCES loan_officers(officer_id)
    );
    CREATE TABLE IF NOT EXISTS risk_assessments (
        risk_assessment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER UNIQUE NOT NULL,
        risk_score DECIMAL(5,4),
        risk_classification VARCHAR(50),
        FOREIGN KEY (application_id) REFERENCES loan_applications(application_id)
    );
    CREATE TABLE IF NOT EXISTS shap_explanations (
        shap_id INTEGER PRIMARY KEY AUTOINCREMENT,
        risk_assessment_id INTEGER UNIQUE NOT NULL,
        plain_language_summary TEXT,
        top_features TEXT,
        FOREIGN KEY (risk_assessment_id) REFERENCES risk_assessments(risk_assessment_id)
    );
    """)
    conn.commit()
    return conn


def get_connection(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_user(conn, username, password, role, managed_by_admin_id=None):
    pw_hash = bcrypt.hashpw(
        password.encode(), bcrypt.gensalt()
    ).decode()

    cur = conn.execute(
        "INSERT INTO users (username, password_hash, role, managed_by_admin_id) VALUES (?,?,?,?)",
        (username, pw_hash, role, managed_by_admin_id)
    )

    conn.commit()
    return cur.lastrowid


def verify_login(conn, username, password):
    row = conn.execute(
        "SELECT user_id, password_hash, role FROM users WHERE username=?",
        (username,)
    ).fetchone()

    if row is None:
        return None

    user_id, pw_hash, role = row

    if len(password.encode()) > 72:
        return None

    if bcrypt.checkpw(password.encode(), pw_hash.encode()):
        return {"user_id": user_id, "role": role}

    return None


def save_application(conn, officer_id, data):
    cur = conn.execute("""
        INSERT INTO loan_applications
        (officer_id, business_name, industry_type, num_employees, business_age,
         loan_amount, loan_term, application_date, application_status)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        officer_id,
        data["business_name"],
        data["industry_type"],
        data["num_employees"],
        data["business_age"],
        data["loan_amount"],
        data["loan_term"],
        data["application_date"],
        "Pending"
    ))

    conn.commit()
    return cur.lastrowid


def save_risk_assessment(conn, application_id, result):
    cur = conn.execute("""
        INSERT INTO risk_assessments
        (application_id, risk_score, risk_classification)
        VALUES (?,?,?)
    """, (
        application_id,
        result["risk_score"],
        result["risk_classification"]
    ))

    conn.commit()
    risk_assessment_id = cur.lastrowid

    conn.execute("""
        INSERT INTO shap_explanations
        (risk_assessment_id, plain_language_summary, top_features)
        VALUES (?,?,?)
    """, (
        risk_assessment_id,
        result["plain_language_summary"],
        result["top_features"]
    ))

    conn.commit()
    return risk_assessment_id


def save_decision(conn, application_id, officer_id, decision, reason=None):
    conn.execute("""
        INSERT INTO decisions
        (application_id, officer_id, decision, decision_reason)
        VALUES (?,?,?,?)
    """, (application_id, officer_id, decision, reason))

    conn.execute(
        "UPDATE loan_applications SET application_status=? WHERE application_id=?",
        (decision, application_id)
    )

    conn.commit()


# ---------- Phase 9b: read functions for the My Applications screen ----------

_APP_SELECT = """
    SELECT la.application_id, la.business_name, la.industry_type, la.num_employees,
           la.business_age, la.loan_amount, la.loan_term, la.application_date,
           la.application_status, ra.risk_score, ra.risk_classification,
           se.plain_language_summary, se.top_features, d.decision, d.decision_reason
    FROM loan_applications la
    LEFT JOIN risk_assessments ra ON ra.application_id = la.application_id
    LEFT JOIN shap_explanations se ON se.risk_assessment_id = ra.risk_assessment_id
    LEFT JOIN decisions d ON d.application_id = la.application_id
"""


def _rows_to_dicts(cur):
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def list_applications(conn, officer_id):
    cur = conn.execute(
        _APP_SELECT + " WHERE la.officer_id = ? ORDER BY la.application_id DESC",
        (officer_id,)
    )

    return _rows_to_dicts(cur)


def get_application(conn, application_id, officer_id):
    """Returns the application only if it belongs to this officer."""

    cur = conn.execute(
        _APP_SELECT + " WHERE la.application_id = ? AND la.officer_id = ?",
        (application_id, officer_id)
    )

    rows = _rows_to_dicts(cur)
    return rows[0] if rows else None


# ---------- Database migration and authentication ----------

def migrate_db(conn):
    """Safely updates the database schema without deleting existing records."""

    with conn:
        conn.execute("BEGIN IMMEDIATE")

        cols = [
            r[1] for r in conn.execute("PRAGMA table_info(users)")
        ]

        if "is_active" not in cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
            )

        if "must_change_password" not in cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0"
            )

        if "session_version" not in cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0"
            )

        conn.execute("""
            UPDATE system_administrators
            SET access_level = 'Full access'
            WHERE LOWER(TRIM(access_level)) IN ('full', 'full access')
              AND access_level != 'Full access'
        """)

        conn.execute("""
            UPDATE system_administrators
            SET access_level = 'Limited access'
            WHERE LOWER(TRIM(access_level)) IN ('limited', 'limited access')
              AND access_level != 'Limited access'
        """)


def authenticate(conn, username, password):
    row = conn.execute("""
        SELECT user_id, password_hash, role,
               is_active, must_change_password, session_version
        FROM users
        WHERE username = ?
    """, (username,)).fetchone()

    if row is None:
        return None

    user_id, pw_hash, role, active, must_change, version = row

    if len(password.encode()) > 72:
        return None

    if not bcrypt.checkpw(password.encode(), pw_hash.encode()):
        return None

    return {
        "user_id": user_id,
        "role": role,
        "active": bool(active),
        "must_change_password": bool(must_change),
        "session_version": version
    }


def is_user_active(conn, user_id):
    row = conn.execute(
        "SELECT is_active FROM users WHERE user_id=?",
        (user_id,)
    ).fetchone()

    return bool(row and row[0])


def get_session_status(conn, user_id):
    """Returns the current account status for session validation."""

    row = conn.execute("""
        SELECT role, is_active,
               must_change_password, session_version
        FROM users
        WHERE user_id = ?
    """, (user_id,)).fetchone()

    if row is None:
        return None

    role, active, must_change, version = row

    return {
        "role": role,
        "active": bool(active),
        "must_change_password": bool(must_change),
        "session_version": version
    }


# ---------- Administrator permissions ----------

def get_admin_id(conn, user_id):
    row = conn.execute(
        "SELECT admin_id FROM system_administrators WHERE user_id=?",
        (user_id,)
    ).fetchone()

    return row[0] if row else None


def get_admin_access_level(conn, user_id):
    """Returns the access level of an active administrator."""

    row = conn.execute("""
        SELECT sa.access_level
        FROM system_administrators sa
        JOIN users u ON sa.user_id = u.user_id
        WHERE u.user_id = ?
          AND u.role = 'admin'
          AND u.is_active = 1
    """, (user_id,)).fetchone()

    if row is None:
        return None

    return row[0]


def has_full_admin_access(conn, user_id):
    """Checks whether a user can manage other accounts."""

    row = conn.execute("""
        SELECT 1
        FROM system_administrators sa
        JOIN users u ON sa.user_id = u.user_id
        WHERE u.user_id = ?
          AND u.role = 'admin'
          AND u.is_active = 1
          AND u.must_change_password = 0
          AND sa.access_level = 'Full access'
    """, (user_id,)).fetchone()

    return row is not None


def require_full_admin_access(conn, user_id):
    """Blocks account management actions by unauthorized users."""

    if not has_full_admin_access(conn, user_id):
        raise PermissionError(
            "Full administrator access is required for this action."
        )


def count_active_full_admins(conn):
    """Counts active administrators with full access."""

    row = conn.execute("""
        SELECT COUNT(DISTINCT u.user_id)
        FROM users u
        JOIN system_administrators sa
            ON u.user_id = sa.user_id
        WHERE u.role = 'admin'
          AND u.is_active = 1
          AND sa.access_level = 'Full access'
    """).fetchone()

    return row[0]


# ---------- User management ----------

def list_users(conn):
    cur = conn.execute("""
        SELECT u.user_id, u.username, u.role, u.is_active,
               COALESCE(lo.branch_office, sa.access_level) AS detail,
               mu.username AS managed_by,
               CASE WHEN lo.officer_id IS NULL THEN NULL
                    ELSE (
                        SELECT COUNT(*)
                        FROM loan_applications la
                        WHERE la.officer_id = lo.officer_id
                    )
               END AS applications
        FROM users u
        LEFT JOIN loan_officers lo ON lo.user_id = u.user_id
        LEFT JOIN system_administrators sa ON sa.user_id = u.user_id
        LEFT JOIN system_administrators msa ON msa.admin_id = u.managed_by_admin_id
        LEFT JOIN users mu ON mu.user_id = msa.user_id
        ORDER BY u.user_id
    """)

    return _rows_to_dicts(cur)


def add_user(
    conn, username, password, role, detail,
    managed_by_admin_id, *, actor_user_id
):
    """Allows a full-access administrator to create a user account."""

    require_full_admin_access(conn, actor_user_id)

    if managed_by_admin_id != get_admin_id(conn, actor_user_id):
        raise PermissionError("Invalid managing administrator.")

    if role not in ("loan_officer", "admin"):
        raise ValueError("Invalid user role.")

    if role == "admin" and detail not in (
        "Full access", "Limited access"
    ):
        raise ValueError("Invalid administrator access level.")

    if len(password) < 8 or len(password.encode()) > 72:
        raise ValueError("Invalid password length.")

    pw_hash = bcrypt.hashpw(
        password.encode(), bcrypt.gensalt()
    ).decode()

    with conn:
        conn.execute("BEGIN IMMEDIATE")

        require_full_admin_access(conn, actor_user_id)

        if managed_by_admin_id != get_admin_id(conn, actor_user_id):
            raise PermissionError("Invalid managing administrator.")

        cur = conn.execute("""
            INSERT INTO users
            (username, password_hash, role,
             managed_by_admin_id, must_change_password)
            VALUES (?, ?, ?, ?, 1)
        """, (
            username,
            pw_hash,
            role,
            managed_by_admin_id
        ))

        user_id = cur.lastrowid

        if role == "loan_officer":
            conn.execute(
                "INSERT INTO loan_officers (user_id, branch_office) VALUES (?,?)",
                (user_id, detail)
            )

        else:
            conn.execute(
                "INSERT INTO system_administrators (user_id, access_level) VALUES (?,?)",
                (user_id, detail)
            )

    return user_id


def set_user_active(conn, user_id, active, *, actor_user_id):
    """Allows authorized administrators to activate or deactivate accounts."""

    with conn:
        conn.execute("BEGIN IMMEDIATE")

        require_full_admin_access(conn, actor_user_id)

        if user_id == actor_user_id and not active:
            raise PermissionError(
                "You cannot deactivate your own account."
            )

        row = conn.execute("""
            SELECT u.role, u.is_active, sa.access_level
            FROM users u
            LEFT JOIN system_administrators sa
                ON u.user_id = sa.user_id
            WHERE u.user_id = ?
        """, (user_id,)).fetchone()

        if row is None:
            raise ValueError("User account not found.")

        role, currently_active, access_level = row

        if (
            not active
            and currently_active
            and role == "admin"
            and access_level == "Full access"
            and count_active_full_admins(conn) <= 1
        ):
            raise PermissionError(
                "At least one active full-access administrator must remain."
            )

        conn.execute("""
            UPDATE users
            SET is_active = ?,
                session_version = session_version + 1
            WHERE user_id = ?
              AND is_active != ?
        """, (
            1 if active else 0,
            user_id,
            1 if active else 0
        ))


# ---------- Password management ----------

def reset_password(conn, user_id, new_password, *, actor_user_id):
    """Allows an authorized administrator to assign a temporary password."""

    require_full_admin_access(conn, actor_user_id)

    if user_id == actor_user_id:
        raise PermissionError(
            "Use Change Password to change your own password."
        )

    if len(new_password) < 8 or len(new_password.encode()) > 72:
        raise ValueError("Invalid password length.")

    pw_hash = bcrypt.hashpw(
        new_password.encode(),
        bcrypt.gensalt()
    ).decode()

    with conn:
        conn.execute("BEGIN IMMEDIATE")

        require_full_admin_access(conn, actor_user_id)

        cursor = conn.execute("""
            UPDATE users
            SET password_hash = ?,
                must_change_password = 1,
                session_version = session_version + 1
            WHERE user_id = ?
        """, (pw_hash, user_id))

        if cursor.rowcount != 1:
            raise ValueError("User account not found.")


def change_password(conn, user_id, current_password, new_password):
    """Allows an active user to securely change their own password."""

    if len(new_password) < 8:
        return False, "The new password must be at least 8 characters."

    if len(new_password.encode()) > 72:
        return False, "The new password is too long."

    if len(current_password.encode()) > 72:
        return False, "The current password is incorrect."

    if current_password == new_password:
        return False, "The new password must differ from the current password."

    row = conn.execute("""
        SELECT password_hash, is_active, session_version
        FROM users
        WHERE user_id = ?
    """, (user_id,)).fetchone()

    if row is None or not row[1]:
        return False, "This account is unavailable."

    old_hash = row[0]
    old_version = row[2]

    if not bcrypt.checkpw(
        current_password.encode(),
        old_hash.encode()
    ):
        return False, "The current password is incorrect."

    new_hash = bcrypt.hashpw(
        new_password.encode(),
        bcrypt.gensalt()
    ).decode()

    cursor = conn.execute("""
        UPDATE users
        SET password_hash = ?,
            must_change_password = 0,
            session_version = session_version + 1
        WHERE user_id = ?
          AND password_hash = ?
          AND is_active = 1
          AND session_version = ?
    """, (
        new_hash,
        user_id,
        old_hash,
        old_version
    ))

    conn.commit()

    if cursor.rowcount != 1:
        return False, "Account details changed. Please try again."

    return True, "Password changed successfully."


def update_user_detail(conn, user_id, detail, *, actor_user_id):
    """Allows authorized administrators to update user account details."""

    with conn:
        conn.execute("BEGIN IMMEDIATE")

        require_full_admin_access(conn, actor_user_id)

        row = conn.execute("""
            SELECT u.role, u.is_active, sa.access_level
            FROM users u
            LEFT JOIN system_administrators sa
                ON u.user_id = sa.user_id
            WHERE u.user_id = ?
        """, (user_id,)).fetchone()

        if row is None:
            raise ValueError("User account not found.")

        role, active, current_access = row

        if role == "loan_officer":
            conn.execute(
                "UPDATE loan_officers SET branch_office=? WHERE user_id=?",
                (detail, user_id)
            )

        elif role == "admin":

            if detail not in ("Full access", "Limited access"):
                raise ValueError(
                    "Invalid administrator access level."
                )

            if user_id == actor_user_id and detail != current_access:
                raise PermissionError(
                    "You cannot change your own access level."
                )

            if (
                active
                and current_access == "Full access"
                and detail == "Limited access"
                and count_active_full_admins(conn) <= 1
            ):
                raise PermissionError(
                    "At least one active full-access administrator must remain."
                )

            conn.execute(
                "UPDATE system_administrators SET access_level=? WHERE user_id=?",
                (detail, user_id)
            )

            if detail != current_access:
                conn.execute("""
                    UPDATE users
                    SET session_version = session_version + 1
                    WHERE user_id = ?
                """, (user_id,))

        else:
            raise ValueError("Invalid user role.")


# ---------- System performance and reporting ----------

def usage_summary(conn):
    from datetime import date, timedelta

    def one(sql, *args):
        return conn.execute(sql, args).fetchone()[0]

    today = date.today()

    return {
        "total": one(
            "SELECT COUNT(*) FROM loan_applications"
        ),
        "today": one(
            "SELECT COUNT(*) FROM loan_applications WHERE application_date = ?",
            today.isoformat()
        ),
        "last7": one(
            "SELECT COUNT(*) FROM loan_applications WHERE application_date >= ?",
            (today - timedelta(days=6)).isoformat()
        ),
        "pending": one(
            "SELECT COUNT(*) FROM loan_applications WHERE application_status = 'Pending'"
        ),
        "approved": one(
            "SELECT COUNT(*) FROM loan_applications WHERE application_status = 'Approved'"
        ),
        "rejected": one(
            "SELECT COUNT(*) FROM loan_applications WHERE application_status = 'Rejected'"
        ),
        "users_total": one(
            "SELECT COUNT(*) FROM users"
        ),
        "users_active": one(
            "SELECT COUNT(*) FROM users WHERE is_active = 1"
        ),
    }


def band_counts(conn):
    rows = conn.execute("""
        SELECT risk_classification, COUNT(*)
        FROM risk_assessments
        GROUP BY risk_classification
    """).fetchall()

    return {r[0]: r[1] for r in rows}


def applications_per_day(conn, days=14):
    from datetime import date, timedelta

    start = date.today() - timedelta(days=days - 1)

    rows = conn.execute("""
        SELECT application_date, COUNT(*)
        FROM loan_applications
        WHERE application_date >= ?
        GROUP BY application_date
    """, (start.isoformat(),)).fetchall()

    counts = {r[0]: r[1] for r in rows}

    out = []

    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        out.append((d, counts.get(d, 0)))

    return out