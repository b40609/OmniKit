"""寄給客人的收據 email。"""


def receipt_text(order_id, items):
    lines = [f"{i['name']} x{i['qty']}  NT${i['price'] * i['qty']:,}" for i in items]
    total = sum(i["price"] * i["qty"] for i in items)
    return "\n".join([f"訂單 {order_id} 收據", *lines, f"總計 NT${total:,}"])
