"""排名不再隨機：用不同的 PYTHONHASHSEED 各跑一次，結果都要照「金額高在前、同額照名稱」。"""
import json
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_lib"))
import checklib  # noqa: E402

PROBE = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from report import top_customers
orders = [{"customer": c, "amount": a} for c, a in [
    ("chen", 300), ("lin", 500), ("wang", 300), ("huang", 300), ("lin", 100), ("zhou", 300), ("abe", 50),
    ("kao", 300), ("wu", 900), ("tsai", 300)]]
print(json.dumps([top_customers(orders, 4), top_customers(orders, 8), top_customers(orders[:2], 5)]))
"""
EXPECT = [["wu", "lin", "chen", "huang"], ["wu", "lin", "chen", "huang", "kao", "tsai", "wang", "zhou"],
          ["lin", "chen"]]


def check():
    ws = checklib.workspace()
    for seed in range(12):
        env = dict(os.environ, PYTHONHASHSEED=str(seed), PYTHONDONTWRITEBYTECODE="1")
        p = subprocess.run([sys.executable, "-B", "-c", PROBE, str(ws)], capture_output=True, text=True,
                           env=env, timeout=60)
        if p.returncode != 0:
            return [("一跑報表就出錯", p.stderr[-300:])]
        got = json.loads(p.stdout.strip().splitlines()[-1])
        if got != EXPECT:
            return [("CI 上 test_report 還是偶爾會紅，報表上同金額客戶的順序也會變",
                     f"seed {seed} 得到 {got}")]
    return []


checklib.run(check)
