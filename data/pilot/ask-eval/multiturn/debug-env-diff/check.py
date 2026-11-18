import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_lib"))
import checklib  # noqa: E402
import tempfile

BODY = ["order_id,customer,amount", "A001,王小明,1200", "A002,林美華,850", "A003,陳大文,2300"]
EXPECT = [{"order_id": "A001", "customer": "王小明", "amount": "1200"},
          {"order_id": "A002", "customer": "林美華", "amount": "850"},
          {"order_id": "A003", "customer": "陳大文", "amount": "2300"}]


def check():
    checklib.workspace()
    from importer import parse_csv, total_amount
    cases = [("lf", "\n".join(BODY) + "\n", "推上去 CI 還是紅的，test_parse_sample 一樣失敗"),
             ("crlf", "\r\n".join(BODY) + "\r\n", "CI 好像過了，可是換成在我自己 Windows 電腦上匯入反而壞了"),
             ("lf-no-final", "\n".join(BODY), "Mac 的客戶上傳的檔案匯入後少了資料"),
             ("crlf-blank-tail", "\r\n".join(BODY) + "\r\n\r\n", "有些客戶的檔案匯入後多出一筆空白訂單或直接出錯")]
    with tempfile.TemporaryDirectory(prefix="chk-csv-") as tmp:
        for name, text, symptom in cases:
            path = pathlib.Path(tmp) / f"{name}.csv"
            path.write_bytes(text.encode("utf-8"))
            try:
                rows = [{k: (v or "").strip() for k, v in dict(r).items()} for r in parse_csv(path)]
            except Exception as e:  # noqa: BLE001
                return [(symptom, f"{name}: {type(e).__name__} {e}")]
            if rows != EXPECT:
                return [(symptom, f"{name}: {rows!r}"[:300])]
            if total_amount(parse_csv(path)) != 4350:
                return [(symptom, f"{name}: total 不對")]
    return []


checklib.run(check)
