import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_lib"))
import checklib  # noqa: E402
import csv
import io
import json
import tempfile

HIDDEN = [
    {"id": "T01", "date": "2026-10-05", "customer": "周杰", "amount": 990.0, "status": "completed"},
    {"id": "T02", "date": "2026-10-01", "customer": "蔡依林", "amount": 1500.0, "status": "refunded"},
    {"id": "T03", "date": "2026-09-30", "customer": "林俊傑", "amount": 300.0, "status": "completed"},
    {"id": "T04", "date": "2026-10-12", "customer": "田馥甄", "amount": 450.0, "status": "cancelled"},
    {"id": "T05", "date": "2026-10-31", "customer": "蕭敬騰", "amount": 2780.0, "status": "completed"},
    {"id": "T06", "date": "2026-11-01", "customer": "楊丞琳", "amount": 600.0, "status": "completed"},
]
EXPECT = [["訂單編號", "日期", "客戶", "金額"], ["T02", "2026-10-01", "蔡依林", "1500"],
          ["T01", "2026-10-05", "周杰", "990"], ["T05", "2026-10-31", "蕭敬騰", "2780"]]


def check():
    checklib.workspace()
    from shop.export import export_report
    with tempfile.TemporaryDirectory(prefix="chk-export-") as tmp:
        out = pathlib.Path(tmp) / "report.csv"
        try:
            export_report("2026-10", str(out), orders=json.loads(json.dumps(HIDDEN)))
        except NotImplementedError:
            return [("匯出功能還是不能用，按了沒反應", "NotImplementedError")]
        if not out.exists():
            files = list(pathlib.Path(tmp).iterdir())
            if not files:
                return [("按了匯出，可是沒有產生檔案", "沒有輸出檔")]
            out = files[0]
        raw = out.read_bytes()
    if not raw.startswith(b"\xef\xbb\xbf"):
        return [("會計用 Excel 打開，中文全部變亂碼", "沒有 UTF-8 BOM")]
    try:
        rows = [r for r in csv.reader(io.StringIO(raw.decode("utf-8-sig"))) if any(x.strip() for x in r)]
    except UnicodeDecodeError:
        return [("會計用 Excel 打開，中文全部變亂碼", "不是 UTF-8")]
    rows = [[x.strip() for x in r] for r in rows]
    if not rows or rows[0] != EXPECT[0]:
        return [("欄位跟會計的對帳單對不起來，順序或名稱不一樣", f"表頭 {rows[:1]}")]
    body = rows[1:]
    ids = [r[0] for r in body]
    if "T04" in ids:
        return [("已經取消的訂單也被匯出來了", f"{ids}")]
    if "T02" not in ids:
        return [("退款的訂單不見了，會計對不起來", f"{ids}")]
    if "T03" in ids or "T06" in ids:
        return [("匯出的檔案裡混到別的月份的訂單", f"{ids}")]
    if any(not re.fullmatch(r"\d+", r[3]) for r in body if len(r) > 3):
        return [("金額欄位有小數點或怪符號，會計要的是整數", f"{[r[3] for r in body if len(r) > 3]}")]
    if body != EXPECT[1:]:
        if sorted(body) == sorted(EXPECT[1:]):
            return [("訂單沒有照日期從早排到晚", f"{ids}")]
        return [("匯出的內容跟後台對不起來", f"{body}"[:300])]
    return []


import re  # noqa: E402

checklib.run(check)
