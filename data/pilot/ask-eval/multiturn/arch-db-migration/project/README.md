# 會員系統

- 建資料庫並套用 migration：`python manage.py migrate --db app.db`
- 塞測試資料：`python seed.py --db app.db`
- migration 放在 migrations/，檔名 NNN_名稱.py，裡面寫 up(conn)。
