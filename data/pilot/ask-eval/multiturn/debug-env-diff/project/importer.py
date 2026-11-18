"""匯入客戶上傳的訂單 CSV。"""


def parse_csv(path):
    """讀 CSV，回傳每列一個 dict（key 是表頭）。"""
    with open(path, "rb") as f:
        text = f.read().decode("utf-8")
    lines = [line for line in text.split("\r\n") if line]
    header = lines[0].split(",")
    return [dict(zip(header, line.split(","))) for line in lines[1:]]


def total_amount(rows):
    return sum(int(r["amount"]) for r in rows)
