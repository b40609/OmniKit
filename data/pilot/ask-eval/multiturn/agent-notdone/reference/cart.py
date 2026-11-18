"""購物車。items = [{"name", "price"（未稅）, "qty"}]"""
from pricing import with_tax


def cart_view(items):
    lines = [{"name": i["name"], "qty": i["qty"], "amount": with_tax(i["price"] * i["qty"])} for i in items]
    return {"lines": lines, "total": with_tax(sum(i["price"] * i["qty"] for i in items))}
