"""每天早上寄電子報。"""


def recipients(conn):
    return [(r["email"], r["full_name"]) for r in conn.execute("SELECT email, full_name FROM users ORDER BY id")]
