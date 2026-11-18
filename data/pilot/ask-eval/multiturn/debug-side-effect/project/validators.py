"""共用的欄位檢查。結帳、會員資料、匯出報表都會用到。"""
import re


def normalize_phone(raw):
    """把手機號碼整理成 10 碼數字（0912345678）；不是台灣手機就回傳 None。"""
    digits = re.sub(r"[\s-]", "", raw or "")
    if re.fullmatch(r"09\d{8}", digits):
        return digits
    return None
