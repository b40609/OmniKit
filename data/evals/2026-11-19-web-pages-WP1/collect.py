"""把三組成品裡頁面實際引用到的檔案搬進 repo（加 NOTES.md、CREDITS.md），工作檔與截圖素材不搬。

用法：python -I collect.py <工作根目錄> <輸出資料夾>
從 site/index.html 開始，掃 HTML、CSS、JS 裡的相對路徑（src、href、url()、import、fetch 字串），一路追下去。
"""
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote

ARMS = ("taste-skill", "huashu-design", "none")
TEXT = {".html", ".css", ".js", ".mjs", ".svg", ".json", ".webmanifest"}
PAT = re.compile(r"""(?:src|href|poster|data-src)\s*=\s*["']([^"'#?]+)|url\(\s*["']?([^"')#?]+)|(?:import|from)\s*["']([^"']+)["']|["']((?:\./|\.\./)?[\w./-]+\.(?:png|jpe?g|webp|avif|gif|svg|mp4|webm|woff2?|ttf|otf|css|js|mjs|json|ico))["']""")


def refs(text):
    for m in PAT.finditer(text):
        v = next(g for g in m.groups() if g)
        v = unquote(v.strip())
        if re.match(r"^[a-zA-Z][\w+.-]*:", v) or v.startswith(("//", "#")) or " " in v or "[" in v:
            continue
        yield v


def collect(site, dst):
    seen, todo = set(), [site / "index.html"]
    while todo:
        f = todo.pop()
        try:
            f = f.resolve()
        except OSError:
            continue
        if f in seen or not f.is_file() or site.resolve() not in f.parents and f != (site / "index.html").resolve():
            continue
        seen.add(f)
        if f.suffix.lower() in TEXT:
            for r in refs(f.read_text(encoding="utf-8", errors="replace")):
                base = site if r.startswith("/") else f.parent
                todo.append(base / r.lstrip("/"))
    for extra in ("NOTES.md", "CREDITS.md", "favicon.svg", "favicon.ico"):
        if (site / extra).is_file():
            seen.add((site / extra).resolve())
    total = 0
    for f in sorted(seen):
        rel = f.relative_to(site.resolve())
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, out)
        total += f.stat().st_size
    return len(seen), total


if __name__ == "__main__":
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    for arm in ARMS:
        dst = out / arm
        if dst.exists():
            raise SystemExit(f"{dst} 已經存在")
        n, size = collect(root / arm / "site", dst)
        print(f"{arm}: {n} 個檔，{size / 1e6:.1f} MB")
