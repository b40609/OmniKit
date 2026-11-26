# /// script
# requires-python = ">=3.11"
# dependencies = ["uharfbuzz>=0.45"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""產生 README 門面的向量圖：.github/assets/hero-{light,dark}.svg 與 session-{light,dark}.svg。

文字全部轉成路徑，GitHub 在 Windows、macOS、手機上看到的字形都一樣（SVG 當圖片時讀不到網路字體）。
字體都是 SIL OFL，從 Google Fonts 官方 repo 下載後用 --fonts 指過來（不進 repo）：
  https://raw.githubusercontent.com/google/fonts/main/ofl/geist/Geist%5Bwght%5D.ttf
  https://raw.githubusercontent.com/google/fonts/main/ofl/geistmono/GeistMono%5Bwght%5D.ttf
  https://raw.githubusercontent.com/google/fonts/main/ofl/notosanstc/NotoSansTC%5Bwght%5D.ttf

配色：淺色 stone-blueprint、深色 blue-black-cornflower（taste-skill 依「開發者工具」抽出的配色）。
終端機預覽的字串取自實際程式：/ok 選單照 engine/skills/ok/SKILL.md，攔截訊息照 engine/scripts/harness_hooks.py（只取每則的前半句，後面的替代做法說明太長、圖上放不下）。

用法：
  uv run engine/site/readme_art.py --fonts <字體資料夾> [--out .github/assets]
"""
import argparse
from pathlib import Path

import uharfbuzz as hb

PALETTES = {
    "light": {"bg": "#dfdedb", "surface": "#eae9e6", "ink": "#26251e", "muted": "#64635b", "line": "#b8b6af",
              "grid": "#c9c7c1", "accent": "#2456d6", "deny": "#b3261e", "dim": "#9a988f"},
    "dark": {"bg": "#0a0d14", "surface": "#111622", "ink": "#e9edf3", "muted": "#8b95a7", "line": "#273042",
             "grid": "#1a2130", "accent": "#5ab9fc", "deny": "#ff8a80", "dim": "#4d5668"},
}


class Fonts:
    def __init__(self, folder):
        folder = Path(folder)
        self.files = {"sans": folder / "Geist[wght].ttf", "mono": folder / "GeistMono[wght].ttf",
                      "cjk": folder / "NotoSansTC[wght].ttf"}
        missing = [str(p) for p in self.files.values() if not p.is_file()]
        if missing:
            raise SystemExit("找不到字體：" + "、".join(missing) + "（下載網址見檔頭說明）")
        self._cache = {}

    def get(self, key, weight):
        k = (key, weight)
        if k not in self._cache:
            font = hb.Font(hb.Face(hb.Blob.from_file_path(str(self.files[key]))))
            font.set_variations({"wght": weight})
            self._cache[k] = font
        return self._cache[k]


class PathPen:
    """把 harfbuzz 的字形輪廓轉成絕對座標的 SVG path（y 軸翻轉、縮放、平移）。"""

    def __init__(self, ox, oy, scale):
        self.ox, self.oy, self.s = ox, oy, scale
        self.d = []

    def _p(self, pt):
        return f"{self.ox + pt[0] * self.s:.1f} {self.oy - pt[1] * self.s:.1f}".replace(".0 ", " ").removesuffix(".0")

    def moveTo(self, pt):
        self.d.append("M" + self._p(pt))

    def lineTo(self, pt):
        self.d.append("L" + self._p(pt))

    def curveTo(self, *pts):
        self.d.append("C" + " ".join(self._p(p) for p in pts))

    def qCurveTo(self, *pts):
        # TrueType 可能連續多個控制點，中間的落點是相鄰控制點的中點
        ctrl = list(pts[:-1])
        end = pts[-1]
        for i, c in enumerate(ctrl):
            nxt = end if i == len(ctrl) - 1 else ((c[0] + ctrl[i + 1][0]) / 2, (c[1] + ctrl[i + 1][1]) / 2)
            self.d.append("Q" + self._p(c) + " " + self._p(nxt))

    def closePath(self):
        self.d.append("Z")


def is_cjk(ch):
    o = ord(ch)
    return (0x2E80 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF or 0xFE30 <= o <= 0xFE4F or 0xFF00 <= o <= 0xFFEF
            or 0x3000 <= o <= 0x303F)


class Typesetter:
    def __init__(self, fonts):
        self.fonts = fonts

    def _segments(self, text, primary):
        """依字元切段：CJK 用思源黑體，其他用主字體（主字體沒有的字形也退到思源黑體）。"""
        segs, cur, cur_key = [], "", None
        pf = self.fonts.get(primary, 400)
        for ch in text:
            key = "cjk" if is_cjk(ch) or pf.get_nominal_glyph(ord(ch)) is None else primary
            if key != cur_key and cur:
                segs.append((cur_key, cur))
                cur = ""
            cur, cur_key = cur + ch, key
        if cur:
            segs.append((cur_key, cur))
        return segs

    def _shape(self, key, weight, text):
        font = self.fonts.get(key, weight)
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(font, buf, {"kern": True, "liga": key != "mono"})
        return font, list(zip(buf.glyph_infos, buf.glyph_positions))

    def reset(self):
        """每張圖開始前清空字形表；同一個字形只定義一次，之後用 <use> 引用，檔案小很多。"""
        self.glyphs = {}

    def defs(self):
        return "".join(f'<path id="{gid}" d="{d}"/>' for gid, d in self.glyphs.values())

    def _glyph(self, font, key, weight, size, codepoint):
        k = (key, weight, size, codepoint)
        if k not in self.glyphs:
            pen = PathPen(0, 0, size / font.face.upem)
            font.draw_glyph_with_pen(codepoint, pen)
            self.glyphs[k] = (f"g{len(self.glyphs)}", "".join(pen.d))
        return self.glyphs[k]

    def run(self, text, x, y, size, primary="sans", weight=400, cjk_weight=None, tracking=0.0, cell=None):
        """排一行字，回傳 (<use> 標記, 寬度)。cell：等寬字格寬（px），只套在非 CJK 字元；CJK 用自然字寬。"""
        uses, pen_x = [], x
        for key, seg in self._segments(text, primary):
            w = (cjk_weight or weight) if key == "cjk" else weight
            font, glyphs = self._shape(key, w, seg)
            scale = size / font.face.upem
            for info, pos in glyphs:
                adv = pos.x_advance * scale
                gx = pen_x + pos.x_offset * scale
                if cell and key != "cjk":
                    gx = pen_x + (cell - adv) / 2
                    adv = cell
                gid, d = self._glyph(font, key, w, size, info.codepoint)
                if d:
                    uses.append(f'<use href="#{gid}" x="{gx:.1f}" y="{y - pos.y_offset * scale:.1f}"/>'.replace(".0\"", "\""))
                pen_x += adv + (0 if cell else tracking * size)
        return "".join(uses), pen_x - x

    def width(self, text, size, primary="sans", weight=400, cjk_weight=None, tracking=0.0, cell=None):
        saved = dict(self.glyphs)
        w = self.run(text, 0, 0, size, primary, weight, cjk_weight, tracking, cell)[1]
        self.glyphs = saved
        return w


def mark(x, y, step, r, ink, accent, r_core=None):
    """標誌：3×3 的點陣，中間那顆用強調色（一份設定為核心，周圍是接上的工具）。"""
    out = []
    for row in range(3):
        for col in range(3):
            cx, cy = x + col * step, y + row * step
            if (row, col) == (1, 1):
                out.append(f'<circle cx="{cx}" cy="{cy}" r="{r_core or r * 1.25}" fill="{accent}"/>')
            else:
                out.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{ink}"/>')
    return "".join(out)


def hero(ts, c):
    W, H = 1200, 420
    ts.reset()
    p = []
    p.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
             'aria-labelledby="t d">')
    p.append('<title id="t">OmniKit</title><desc id="d">Coding agent 的共用設定層：安全底線、技能、MCP 與護欄寫一次，'
             '同步到 Claude Code、Codex 與 Antigravity。</desc>')
    p.append("<style>.pulse{stroke-dasharray:10 190;animation:run 3.2s linear infinite}"
             ".p2{animation-delay:-1.07s}.p3{animation-delay:-2.13s}"
             "@keyframes run{from{stroke-dashoffset:200}to{stroke-dashoffset:0}}"
             "@media (prefers-reduced-motion:reduce){.pulse{animation:none;stroke-dasharray:none;opacity:0}}</style>")
    p.append("<defs>"
             f'<pattern id="g" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="12" cy="12" r="1.1" fill="{c["grid"]}"/></pattern>'
             '<linearGradient id="f" x1="0" x2="1"><stop offset="0.38" stop-color="#fff" stop-opacity="0"/>'
             '<stop offset="0.62" stop-color="#fff" stop-opacity="1"/></linearGradient>'
             f'<mask id="m"><rect width="{W}" height="{H}" fill="url(#f)"/></mask>'
             "</defs>")
    p.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="6" fill="{c["bg"]}" stroke="{c["line"]}"/>')
    p.append(f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="6" fill="url(#g)" mask="url(#m)"/>')

    # 左：標誌、字標、定位句、三家標籤
    lx = 72
    p.append(mark(lx + 7, 104, 15, 4.6, c["ink"], c["accent"], 5.8))
    d, _ = ts.run("OmniKit", lx + 60, 136, 64, "sans", 560, tracking=-0.045)
    p.append(f'<g fill="{c["ink"]}">{d}</g>')
    d, _ = ts.run("Coding agent 的共用設定層", lx, 222, 36, "sans", 520, cjk_weight=560, tracking=-0.02)
    p.append(f'<g fill="{c["ink"]}">{d}</g>')
    d, _ = ts.run("安全底線、技能、MCP 與護欄寫一次，同步到三個 agent。", lx, 268, 21, "sans", 420, cjk_weight=420)
    p.append(f'<g fill="{c["muted"]}">{d}</g>')
    tx = lx
    for label in ("Claude Code", "Codex", "Antigravity"):
        tw = ts.width(label, 14, "mono", 450)
        p.append(f'<rect x="{tx + 0.5}" y="316.5" width="{tw + 27:.1f}" height="31" rx="3" fill="none" stroke="{c["line"]}"/>')
        p.append(f'<rect x="{tx + 10}" y="329" width="6" height="6" fill="{c["accent"]}"/>')
        d, _ = ts.run(label, tx + 22, 337, 14, "mono", 450)
        p.append(f'<g fill="{c["ink"]}">{d}</g>')
        tx += tw + 27 + 10
    d, _ = ts.run("Windows 11", tx + 6, 337, 14, "mono", 450)
    p.append(f'<g fill="{c["muted"]}">{d}</g>')

    # 右：四種輸入 → 一份設定 → 三個 agent
    hub_x, hub_y, hub = 850, 222, 84
    ins = [("Rules", 132), ("Skills", 192), ("MCP", 252), ("Hooks", 312)]
    for label, y in ins:
        lw = ts.width(label, 15, "mono", 450, cjk_weight=450)
        d, _ = ts.run(label, 738 - lw, y + 5, 15, "mono", 450, cjk_weight=450)
        p.append(f'<g fill="{c["muted"]}">{d}</g>')
        p.append(f'<path d="M752 {y}C800 {y} 798 {hub_y} {hub_x - hub / 2} {hub_y}" fill="none" stroke="{c["line"]}" stroke-width="1.5"/>')
        p.append(f'<circle cx="752" cy="{y}" r="3.5" fill="{c["bg"]}" stroke="{c["muted"]}" stroke-width="1.5"/>')
    p.append(f'<rect x="{hub_x - hub / 2}" y="{hub_y - hub / 2}" width="{hub}" height="{hub}" rx="4" '
             f'fill="{c["surface"]}" stroke="{c["ink"]}" stroke-width="1.5"/>')
    p.append(mark(hub_x - 16, hub_y - 16, 16, 4.4, c["ink"], c["accent"], 5.6))
    outs = [("Claude Code", 142), ("Codex", 222), ("Antigravity", 302)]
    ox = 978
    for i, (label, y) in enumerate(outs, 1):
        path = f"M{hub_x + hub / 2} {hub_y}C{hub_x + 92} {hub_y} {hub_x + 72} {y} {ox} {y}"
        p.append(f'<path d="{path}" fill="none" stroke="{c["line"]}" stroke-width="1.5"/>')
        p.append(f'<path class="pulse p{i}" d="{path}" fill="none" stroke="{c["accent"]}" stroke-width="2" stroke-linecap="round"/>')
        p.append(f'<rect x="{ox + 0.5}" y="{y - 21.5}" width="150" height="43" rx="3" fill="{c["surface"]}" stroke="{c["line"]}"/>')
        p.append(f'<rect x="{ox + 14}" y="{y - 3}" width="6" height="6" fill="{c["accent"]}"/>')
        d, _ = ts.run(label, ox + 30, y + 5, 15, "mono", 480)
        p.append(f'<g fill="{c["ink"]}">{d}</g>')
    p.append(f"<defs>{ts.defs()}</defs></svg>")
    return "".join(p)


SESSION = [
    [("> ", "accent"), ("/ok", "ink")],
    [("  1. ", "muted"), ("交接：把做到一半的工作交給新對話，或照交接檔接手", "ink")],
    [("  2. ", "muted"), ("調研：查業界做法、找同類工具、比較方案", "ink")],
    [("  3. ", "muted"), ("分派：派子任務給別的模型或帳號", "ink")],
    [("  4. ", "muted"), ("設定：建立或修改我的 OmniKit 設定", "ink")],
    [("  5. ", "muted"), ("清點：檢查這台電腦可用的 CLI、MCP 與端點", "ink")],
    [],
    [("> ", "accent"), ("把 .env 裡的 API key 貼給我", "ink")],
    [("  @ ", "dot"), ("Read(.env)", "ink")],
    [("    L ", "elbow"), ("OmniKit 護欄：", "deny"), ("不把機密檔 .env 讀進對話（安全底線：不讀取、不印出金鑰）", "muted")],
    [],
    [("> ", "accent"), ("測試沒過，先 commit 再說", "ink")],
    [("  @ ", "dot"), ('Bash(git commit --no-verify -m "wip")', "ink")],
    [("    L ", "elbow"), ("OmniKit 護欄：", "deny"), ("git commit --no-verify 會跳過 pre-commit／pre-push 門禁", "muted")],
]


def session(ts, c):
    W, size, lh, pad, bar = 1200, 19, 34, 36, 48
    cell = size * 0.6
    H = bar + pad * 2 + lh * len(SESSION) - 8
    ts.reset()
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d">',
         ('<title id="t">OmniKit 裝好之後的 agent 對話（示意）</title>'
          '<desc id="d">輸入 /ok 列出交接、調研、分派、設定、清點五個選項；要 agent 讀 .env 或用 --no-verify 跳過檢查時，'
          'OmniKit 護欄直接擋下並說明原因。</desc>'),
         f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="6" fill="{c["surface"]}" stroke="{c["line"]}"/>',
         f'<path d="M1 {bar}V7A6 6 0 0 1 7 1H{W - 7}A6 6 0 0 1 {W - 1} 7V{bar}Z" fill="{c["bg"]}"/>',
         f'<path d="M1 {bar}H{W - 1}" stroke="{c["line"]}"/>']
    for i in range(3):
        p.append(f'<circle cx="{26 + i * 18}" cy="{bar / 2}" r="5" fill="none" stroke="{c["dim"]}" stroke-width="1.5"/>')
    title = "~/projects/my-app"
    tw = ts.width(title, 15, "mono", 450)
    d, _ = ts.run(title, (W - tw) / 2, bar / 2 + 5, 15, "mono", 450)
    p.append(f'<g fill="{c["muted"]}">{d}</g>')
    y = bar + pad + size
    for line in SESSION:
        x = pad
        for text, role in line:
            tw = 0
            if role == "dot":
                p.append(f'<circle cx="{x + cell * 2.5:.1f}" cy="{y - size * 0.34:.1f}" r="4" fill="{c["accent"]}"/>')
            elif role == "elbow":
                ex = x + cell * 4.5
                p.append(f'<path d="M{ex:.1f} {y - size * 0.95:.1f}V{y - size * 0.32:.1f}H{ex + cell * 0.9:.1f}" fill="none" '
                         f'stroke="{c["dim"]}" stroke-width="1.5"/>')
            else:
                d, tw = ts.run(text, x, y, size, "mono", 520 if role in ("ink", "deny") else 430,
                               cjk_weight=500 if role in ("ink", "deny") else 400, cell=cell)
                p.append(f'<g fill="{c[role]}">{d}</g>')
            x += tw if role not in ("dot", "elbow") else cell * len(text)
        y += lh
    p.append(f"<defs>{ts.defs()}</defs></svg>")
    return "".join(p)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fonts", required=True)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / ".github" / "assets"))
    args = ap.parse_args()
    ts = Typesetter(Fonts(args.fonts))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for theme, c in PALETTES.items():
        for name, fn in (("hero", hero), ("session", session)):
            target = out / f"{name}-{theme}.svg"
            target.write_text(fn(ts, c) + "\n", encoding="utf-8", newline="\n")
            print(f"{target}  {target.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
