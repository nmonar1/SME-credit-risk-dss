from database import get_connection, create_user

conn = get_connection()

admin_user_id = create_user(conn, "a.njeri", "ChangeThisPassword1", "admin")
cur = conn.execute("INSERT INTO system_administrators (user_id, access_level) VALUES (?,?)",
                    (admin_user_id, "full"))
conn.commit()
admin_id = cur.lastrowid

officer_user_id = create_user(conn, "j.mwangi", "ChangeThisPassword2", "loan_officer",
                               managed_by_admin_id=admin_id)
conn.execute("INSERT INTO loan_officers (user_id, branch_office) VALUES (?,?)",
             (officer_user_id, "Nairobi CBD"))
conn.commit()

print("Seeded admin a.njeri and loan officer j.mwangi")