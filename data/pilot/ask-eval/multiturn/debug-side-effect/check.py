"""結帳要收 +886 等寫法；會員資料存 10 碼、匯出顯示 0912-345-678 不能壞；亂打的要擋。"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_lib"))
import checklib  # noqa: E402

OK = ["0912345678", "0912-345-678", "0912 345 678", "+886912345678", "+886 912-345-678", "+886-912-345-678"]
BAD = ["12345", "0812345678", "091234567", "abc", "", "+886 12345"]


def check():
    checklib.workspace()
    from checkout import validate_checkout
    from export import export_rows, format_phone
    from profile import save_profile
    p = []
    for raw in OK:
        if "phone" in validate_checkout({"name": "Amy", "phone": raw}):
            p.append((f"結帳頁還是不收「{raw}」這種寫法", f"checkout 擋掉 {raw!r}"))
    for raw in BAD:
        if "phone" not in validate_checkout({"name": "Amy", "phone": raw}):
            p.append((f"結帳頁連「{raw or '空白'}」這種不是手機的也收了", f"checkout 收了 {raw!r}"))
    for raw in OK:
        try:
            got = save_profile({}, 1, {"name": "Amy", "phone": raw})["phone"]
        except Exception as e:  # noqa: BLE001
            got = f"錯誤 {e}"
        if got != "0912345678":
            p.append(("會員資料頁存起來的手機號碼變得怪怪的（不是 0912345678 這種 10 碼）",
                      f"profile {raw!r} -> {got!r}"))
            break
    for raw in OK:
        got = format_phone(raw)
        if got != "0912-345-678":
            p.append(("匯出報表的手機欄位格式跑掉了", f"format_phone {raw!r} -> {got!r}"))
            break
    if export_rows({1: {"name": "Amy", "phone": "0912345678"}}) != [[1, "Amy", "0912-345-678"]]:
        p.append(("匯出報表的手機欄位格式跑掉了", "export_rows 不對"))
    return p


checklib.run(check)
