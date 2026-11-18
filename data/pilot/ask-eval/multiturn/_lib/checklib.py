"""多輪題 check.py 共用的小工具。check 只讀工作資料夾，不寫入（呼叫端用 -B 關掉 __pycache__）。"""
import json
import pathlib
import sys
import traceback


def workspace() -> pathlib.Path:
    ws = pathlib.Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(ws))
    return ws


def done(problems):
    """problems：[(症狀, 細節)]，空的就是通過。只回報第一個症狀，跟真人一次看到一件事一樣。"""
    if problems:
        symptom, detail = problems[0]
        print(json.dumps({"pass": False, "symptom": symptom, "detail": detail,
                          "all": [d for _, d in problems]}, ensure_ascii=False))
    else:
        print(json.dumps({"pass": True, "symptom": "", "detail": "全部通過"}, ensure_ascii=False))


def run(fn):
    """fn() 回傳 problems；fn 本身出錯（匯入失敗、語法錯）當作程式壞掉。"""
    try:
        problems = fn()
    except Exception as e:  # noqa: BLE001
        problems = [("一用就直接出錯，畫面跳錯誤訊息", f"{type(e).__name__}: {e} | "
                     + traceback.format_exc(limit=3).replace("\n", " ")[-400:])]
    done(problems)
