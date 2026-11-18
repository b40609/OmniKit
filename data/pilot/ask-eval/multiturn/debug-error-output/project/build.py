"""產生產品目錄頁：讀 data/products.json，輸出 dist/index.html。"""
import json
import pathlib

from site_templates import render_page

HERE = pathlib.Path(__file__).resolve().parent


def main(out_dir=None):
    products = json.loads((HERE / "data" / "products.json").read_text(encoding="utf-8"))
    out = pathlib.Path(out_dir) if out_dir else HERE / "dist"
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render_page(products), encoding="utf-8")
    print(f"done: {len(products)} products -> {out / 'index.html'}")


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else None)
