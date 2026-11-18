"""訂單資料。"""
import json
import pathlib

DATA = pathlib.Path(__file__).resolve().parent.parent / "data" / "orders.json"


def load_orders(path=DATA):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
