import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_lib"))
import checklib  # noqa: E402
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_lib"))
import css  # noqa: E402

KPI = "kpi-value"
LABEL = "kpi-label"


def check():
    ws = checklib.workspace()
    d = ws / "dashboard"
    html = (d / "index.html").read_text(encoding="utf-8")
    sheet = css.Sheet.from_html(html, d)
    p = []
    for word in ("昨日營收", "訂單數", "退貨率", "新會員", "1,284,500", "3,912", "2.3%", "418"):
        if word not in html:
            p.append(("原本的指標內容不見了", f"缺 {word}"))
            return p
    # 1. 最重要的數字要最顯眼
    value_sizes = sheet.sizes_for(KPI)
    label_sizes = sheet.sizes_for(LABEL)
    if not value_sizes or min(value_sizes) < 24 or (label_sizes and min(value_sizes) <= max(label_sizes)):
        p.append(("最重要的數字還是不顯眼，標題字跟數字差不多大或更大",
                  f"kpi-value {value_sizes} kpi-label {label_sizes}"))
    # 2. 淡色字
    bg = sheet.card_background()
    worst = sheet.worst_contrast(bg)
    if worst and worst[0] < 4.5:
        p.append(("還是有些字很淡、灰灰的看不清楚", f"對比 {worst[0]:.2f}（{worst[1]}）"))
    # 3. 卡片不齊
    paddings = sheet.values_for("card", "padding")
    widths = sheet.values_for("card", "width")
    inline = css.inline_box_styles(html, "card")
    floats = sheet.values_for("card", "float")
    layout = sheet.layout_of("cards")
    if len(set(paddings)) > 1 or len(set(widths)) > 1 or inline or (floats and layout not in ("grid", "flex")):
        p.append(("四張卡片大小、間距還是不一樣，排起來不齊",
                  f"padding {paddings} width {widths} inline {inline} float {floats} layout {layout}"))
    # 4. 字級太多
    sizes = sheet.distinct_font_sizes()
    if len(sizes) > 5:
        p.append(("字的大小還是大大小小一堆，看起來很亂", f"{len(sizes)} 種字級：{sorted(sizes)}"))
    return p


checklib.run(check)
