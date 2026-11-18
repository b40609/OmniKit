"""價格顯示。"""


def format_price(price):
    value = int(str(price).replace(",", "").strip())
    return f"NT${value:,}"
