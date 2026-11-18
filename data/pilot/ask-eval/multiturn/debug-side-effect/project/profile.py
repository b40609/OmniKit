"""會員資料頁：存檔時把手機整理成 10 碼。"""
from validators import normalize_phone


def save_profile(db, user_id, form):
    phone = normalize_phone(form.get("phone"))
    if phone is None:
        raise ValueError("手機號碼格式不正確")
    db[user_id] = {"name": form.get("name", ""), "phone": phone}
    return db[user_id]
