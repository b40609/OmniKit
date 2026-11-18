import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_lib"))
import checklib  # noqa: E402
import re

ITEMS = [{"name": "馬克杯", "price": 333, "qty": 1}, {"name": "杯墊", "price": 111, "qty": 3},
         {"name": "茶葉", "price": 1250, "qty": 2}]
# 未稅 333 + 333 + 2500 = 3166；含稅總額 round(3166*1.05)=3324（逐項含稅再加會是 350+350+2625=3325）
TOTAL = 3324
LINES = {"馬克杯": 350, "杯墊": 350, "茶葉": 2625}


def check():
    checklib.workspace()
    from cart import cart_view
    from product_page import price_label
    from receipt import receipt_text
    if price_label({"price": 1000}) != "NT$1,050" or price_label({"price": 333}) != "NT$350":
        return [("商品頁的價格不對了", f"{price_label({'price': 1000})}")]
    view = cart_view([dict(i) for i in ITEMS])
    amounts = {line["name"]: line.get("amount") for line in view["lines"]}
    if view["total"] != TOTAL:
        hint = "還是未稅的" if view["total"] == 3166 else "跟發票對不起來"
        return [(f"購物車總額{hint}（顯示 {view['total']:,}）", f"total {view['total']} 期望 {TOTAL}")]
    if any(amounts.get(k) != v for k, v in LINES.items()):
        return [("購物車裡每一項的金額還是未稅的", f"{amounts}")]
    text = receipt_text("A1", [dict(i) for i in ITEMS])
    m = re.search(r"總計\s*NT\$([\d,]+)", text)
    if not m or int(m.group(1).replace(",", "")) != TOTAL:
        return [("客人收到的收據 email，總計金額跟購物車不一樣", text[-120:])]
    for name, v in LINES.items():
        if f"NT${v:,}" not in text:
            return [("客人收到的收據 email，品項金額還是未稅的", text[:200])]
    return []


checklib.run(check)
