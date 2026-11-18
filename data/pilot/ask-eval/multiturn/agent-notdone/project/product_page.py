"""商品頁。"""
from pricing import with_tax


def price_label(product):
    return f"NT${with_tax(product['price']):,}"
