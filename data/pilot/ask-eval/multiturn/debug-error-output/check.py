"""build.py 跑得過；每個價格都是 NT$1,200 格式（含資料夾裡的商品與新加的寫法）。"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_lib"))
import checklib  # noqa: E402

PRODUCTS = [{"name": "登山背包", "price": "2,680"}, {"name": "頭燈", "price": "890"},
            {"name": "睡袋", "price": "3,450"}, {"name": "露營椅", "price": 1200},
            {"name": "保溫瓶", "price": "650"}, {"name": "帳篷", "price": 12800}, {"name": "營燈", "price": "1500"}]
EXPECT = {"登山背包": "NT$2,680", "頭燈": "NT$890", "睡袋": "NT$3,450", "露營椅": "NT$1,200", "保溫瓶": "NT$650",
          "帳篷": "NT$12,800", "營燈": "NT$1,500"}


def check():
    ws = checklib.workspace()
    with tempfile.TemporaryDirectory(prefix="chk-build-") as tmp:
        copy = pathlib.Path(tmp) / "ws"
        shutil.copytree(ws, copy, ignore=shutil.ignore_patterns(".git", "dist", "__pycache__"))
        (copy / "data" / "products.json").write_text(json.dumps(PRODUCTS, ensure_ascii=False), encoding="utf-8")
        p = subprocess.run([sys.executable, "-B", "build.py"], cwd=copy, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        if p.returncode != 0:
            return [("跑 python build.py 還是噴一堆紅字失敗", (p.stderr or p.stdout)[-300:])]
        html_file = copy / "dist" / "index.html"
        if not html_file.exists():
            return [("build 跑完了，可是找不到 dist/index.html", "沒有輸出檔")]
        html = html_file.read_text(encoding="utf-8")
    for name, price in EXPECT.items():
        if name not in html:
            return [(f"頁面上找不到「{name}」這個商品", f"缺 {name}")]
        seg = html.split(name, 1)[1][:200]
        if price not in seg:
            return [(f"「{name}」的價格顯示不對，應該要像 {price} 這樣", f"{name} 附近沒有 {price}：{seg[:120]!r}")]
    return []


checklib.run(check)
