"""結帳頁表單。"""
from validators import normalize_phone


def validate_checkout(form):
    errors = {}
    if not form.get("name"):
        errors["name"] = "請填姓名"
    if normalize_phone(form.get("phone")) is None:
        errors["phone"] = "手機號碼格式不正確"
    return errors
