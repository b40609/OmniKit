COMPOUND = ("歐陽", "司馬", "諸葛", "上官")


def split_name(full):
    full = (full or "").strip()
    if not full:
        return "", ""
    if full.isascii():
        parts = full.split()
        return (" ".join(parts[:-1]), parts[-1]) if len(parts) > 1 else (full, "")
    if len(full) == 1:
        return full, ""
    for s in COMPOUND:
        if full.startswith(s) and len(full) > len(s):
            return full[len(s):], s
    return full[1:], full[0]


def up(conn):
    conn.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
    conn.execute("ALTER TABLE users ADD COLUMN last_name TEXT")
    rows = conn.execute("SELECT id, full_name FROM users").fetchall()
    for r in rows:
        first, last = split_name(r[1])
        conn.execute("UPDATE users SET first_name = ?, last_name = ? WHERE id = ?", (first, last, r[0]))
