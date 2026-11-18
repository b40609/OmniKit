"""頁面模板。"""
from pricing import format_price


def render_card(p):
    return (f'<div class="card"><h2>{p["name"]}</h2>'
            f'<p class="price">{format_price(p["price"])}</p></div>')


def render_page(products):
    cards = "\n".join(render_card(p) for p in products)
    return f"<!doctype html><html><body><h1>產品目錄</h1>\n{cards}\n</body></html>\n"
