"""購物車。items = [{"name", "price"（未稅）, "qty"}]"""


def line_total(item):
    return item["price"] * item["qty"]


def cart_view(items):
    lines = [{"name": i["name"], "qty": i["qty"], "amount": line_total(i)} for i in items]
    return {"lines": lines, "total": sum(line["amount"] for line in lines)}
