"""會員 API。"""


def get_user(conn, user_id):
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def create_user(conn, email, full_name):
    cur = conn.execute("INSERT INTO users (email, full_name) VALUES (?, ?)", (email, full_name))
    conn.commit()
    return cur.lastrowid
