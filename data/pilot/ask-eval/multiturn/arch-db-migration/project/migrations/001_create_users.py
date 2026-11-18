def up(conn):
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE, "
                 "full_name TEXT NOT NULL)")
