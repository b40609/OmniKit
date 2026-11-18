"""給畫面題 check.py 用的極簡 CSS 解析：規則、CSS 變數、字級換算、顏色對比。

只求夠用：不處理 @import、巢狀 CSS、:is() 之類的選擇器邏輯。@media 裡的規則另外標記，
padding、寬度、字級種類這類「整齊度」檢查只看一般規則（手機版改小是合理的）。
"""
import colorsys
import re

NAMED = {"white": "#ffffff", "black": "#000000", "gray": "#808080", "grey": "#808080", "silver": "#c0c0c0",
         "darkgray": "#a9a9a9", "darkgrey": "#a9a9a9", "dimgray": "#696969", "dimgrey": "#696969",
         "lightgray": "#d3d3d3", "lightgrey": "#d3d3d3", "gainsboro": "#dcdcdc", "whitesmoke": "#f5f5f5",
         "red": "#ff0000", "green": "#008000", "blue": "#0000ff", "navy": "#000080", "slategray": "#708090",
         "darkslategray": "#2f4f4f", "orange": "#ffa500", "teal": "#008080"}
KEYWORD_SIZES = {"xx-small": 9, "x-small": 10, "small": 13, "medium": 16, "large": 18, "x-large": 24,
                 "xx-large": 32}


def strip_comments(text):
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def parse_rules(text):
    """回傳 [(selector, {prop: value}, in_media)]；用大括號深度追蹤 @media。"""
    text = strip_comments(text)
    rules, stack, buf, i = [], [], "", 0
    while i < len(text):
        c = text[i]
        if c == "{":
            stack.append(buf.strip())
            buf = ""
        elif c == "}":
            head = stack.pop() if stack else ""
            if head.startswith("@"):
                buf = ""
            else:
                decls = {}
                for part in buf.split(";"):
                    if ":" in part:
                        k, v = part.split(":", 1)
                        decls[k.strip().lower()] = re.sub(r"\s*!important\s*$", "", v.strip())
                in_media = any(h.startswith("@media") for h in stack)
                if not any(h.startswith("@") and not h.startswith("@media") and not h.startswith("@supports")
                           for h in stack):
                    rules.append((head, decls, in_media))
                buf = ""
        else:
            buf += c
        i += 1
    return rules


def has_class(selector, cls):
    """選擇器（任一個逗號分段）的最後一個複合選擇器有 .cls 這個 class。"""
    for part in selector.split(","):
        last = re.split(r"[\s>+~]+", part.strip())[-1] if part.strip() else ""
        if re.search(r"\." + re.escape(cls) + r"(?![\w-])", last):
            return True
    return False


def mentions_class(selector, cls):
    return re.search(r"\." + re.escape(cls) + r"(?![\w-])", selector) is not None


def parse_color(v):
    if not v:
        return None
    v = v.strip().lower()
    v = NAMED.get(v, v)
    m = re.fullmatch(r"#([0-9a-f]{3,8})", v)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(ch * 2 for ch in h)
        if len(h) not in (6, 8):
            return None
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)
    m = re.fullmatch(r"rgba?\(([^)]*)\)", v)
    if m:
        nums = re.findall(r"[\d.]+%?", m.group(1))
        if len(nums) < 3:
            return None
        rgb = [float(n[:-1]) * 2.55 if n.endswith("%") else float(n) for n in nums[:3]]
        a = nums[3] if len(nums) > 3 else "1"
        a = float(a[:-1]) / 100 if a.endswith("%") else float(a)
        return (*[int(round(x)) for x in rgb], a)
    m = re.fullmatch(r"hsla?\(([^)]*)\)", v)
    if m:
        nums = re.findall(r"[\d.]+", m.group(1))
        if len(nums) < 3:
            return None
        r, g, b = colorsys.hls_to_rgb(float(nums[0]) / 360, float(nums[2]) / 100, float(nums[1]) / 100)
        return (int(r * 255), int(g * 255), int(b * 255), float(nums[3]) if len(nums) > 3 else 1.0)
    return None


def luminance(rgb):
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb[:3]
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(fg, bg):
    if len(fg) > 3 and fg[3] < 1:
        a = fg[3]
        fg = tuple(int(fg[i] * a + bg[i] * (1 - a)) for i in range(3))
    la, lb = luminance(fg), luminance(bg)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def size_px(v):
    if v is None:
        return None
    v = v.strip().lower()
    if v in KEYWORD_SIZES:
        return KEYWORD_SIZES[v]
    m = re.match(r"(clamp|max|min)\((.*)\)$", v)
    if m:
        vals = [size_px(x) for x in m.group(2).split(",")]
        vals = [x for x in vals if isinstance(x, (int, float))]
        if not vals:
            return v
        return max(vals) if m.group(1) in ("clamp", "max") else min(vals)
    m = re.match(r"calc\((.*)\)$", v)
    if m:
        found = re.search(r"[\d.]+(px|rem|em|pt)", m.group(1))
        return size_px(found.group(0)) if found else v
    m = re.fullmatch(r"([\d.]+)(px|rem|em|pt|%)?", v)
    if not m:
        return v
    n = float(m.group(1))
    unit = m.group(2) or "px"
    return round({"px": n, "rem": n * 16, "em": n * 16, "pt": n * 4 / 3, "%": n * 16 / 100}[unit], 1)


class Sheet:
    def __init__(self, texts, inline=""):
        self.rules = []
        for t in texts:
            self.rules += parse_rules(t)
        self.vars = {}
        for sel, decls, _ in self.rules:
            for k, v in decls.items():
                if k.startswith("--"):
                    self.vars[k] = v
        self.rules = [(s, {k: self.resolve(v) for k, v in d.items()}, m) for s, d, m in self.rules]
        self.inline = inline

    @classmethod
    def from_html(cls, html, base_dir):
        texts = re.findall(r"<style[^>]*>(.*?)</style>", html, re.S | re.I)
        for href in re.findall(r"<link[^>]+href=\"([^\"]+\.css)\"", html, re.I):
            p = base_dir / href
            if p.exists():
                texts.append(p.read_text(encoding="utf-8"))
        inline = "\n".join(re.findall(r"style=\"([^\"]*)\"", html))
        return cls(texts, inline)

    def resolve(self, v, depth=0):
        if depth > 8 or "var(" not in v:
            return v

        def sub(m):
            name, _, fallback = m.group(1).partition(",")
            return self.vars.get(name.strip(), fallback.strip())
        return self.resolve(re.sub(r"var\(([^()]*)\)", sub, v), depth + 1)

    def plain(self):
        return [(s, d) for s, d, m in self.rules if not m]

    def sizes_for(self, cls):
        return [size_px(d["font-size"]) for s, d in self.plain() if has_class(s, cls) and "font-size" in d]

    def values_for(self, cls, prop):
        out = []
        for s, d in self.plain():
            if has_class(s, cls) and not re.search(r":(hover|focus|active)", s):
                for k, v in d.items():
                    if k == prop or k.startswith(prop + "-"):
                        out.append(k + ":" + re.sub(r"\s+", " ", v))
        return out

    def layout_of(self, cls):
        for s, d in self.plain():
            if has_class(s, cls) and "display" in d:
                return d["display"].split()[0]
        return None

    def card_background(self):
        bg = None
        for s, d in self.plain():
            if s.strip() in ("body", "html", ":root") or has_class(s, "card"):
                c = parse_color(d.get("background-color") or (d.get("background") or "").split(" ")[0])
                if c and c[3] >= 0.99:
                    bg = c if has_class(s, "card") or bg is None else bg
        return bg or (255, 255, 255, 1.0)

    def worst_contrast(self, bg):
        worst = None
        for s, d, _ in self.rules:
            if "color" not in d or "background" in d or "background-color" in d:
                continue
            c = parse_color(d["color"])
            if not c:
                continue
            r = contrast(c, bg)
            if worst is None or r < worst[0]:
                worst = (r, f"{s.strip()} {{color: {d['color']}}}")
        for v in re.findall(r"(?<![-\w])color\s*:\s*([^;]+)", self.inline):
            c = parse_color(v)
            if c:
                r = contrast(c, bg)
                if worst is None or r < worst[0]:
                    worst = (r, f"style=color:{v}")
        return worst

    def distinct_font_sizes(self):
        sizes = {size_px(d["font-size"]) for s, d in self.plain() if "font-size" in d}
        sizes |= {size_px(v) for v in re.findall(r"font-size\s*:\s*([^;]+)", self.inline)}
        return {s for s in sizes if s not in (None, "inherit", "initial", "unset")}


def inline_box_styles(html, cls):
    out = []
    for m in re.finditer(r"<[^>]*class=\"([^\"]*)\"[^>]*>", html):
        tag = m.group(0)
        if cls in m.group(1).split():
            st = re.search(r"style=\"([^\"]*)\"", tag)
            if st and re.search(r"padding|margin|width|height", st.group(1)):
                out.append(st.group(1))
    return out
