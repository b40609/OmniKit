"""登入逾時：一般登入有操作就一直有效、閒置 8 小時才過期；記住我 30 天。"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_lib"))
import checklib  # noqa: E402

H = 60 * 60
D = 24 * H


def check():
    checklib.workspace()
    from auth.session import create_session, is_valid
    from auth.middleware import handle_request
    p = []
    s = create_session("amy", at=0)
    t = 0
    alive = True
    for t in range(10 * 60, 10 * H, 10 * 60):  # 每 10 分鐘操作一次，持續 10 小時
        if handle_request(s, at=t)["status"] != 200:
            alive = False
            break
    if not alive:
        p.append(("登入後一直在操作，大約 %d 分鐘就被踢出去重新登入" % (t // 60), f"一般登入在 t={t}s 被登出"))
    s = create_session("amy", at=0)
    handle_request(s, at=H)
    if not is_valid(s, at=H + 8 * H - 60):
        p.append(("最後一次操作後還不到 8 小時就被登出", "touch 後 8 小時內失效"))
    if is_valid(s, at=H + 8 * H + 60):
        p.append(("放著 8 小時以上沒動，回來還是登入狀態", "閒置超過 8 小時仍有效"))
    r = create_session("bob", remember=True, at=0)
    if handle_request(r, at=20 * H)["status"] != 200 or handle_request(r, at=20 * H + 25 * D)["status"] != 200:
        p.append(("勾了「記住我」，隔天還是要重新登入", "記住我在 30 天內失效"))
    r = create_session("bob", remember=True, at=0)
    if is_valid(r, at=31 * D):
        p.append(("勾了「記住我」一個多月沒來，回來還是登入狀態", "記住我超過 30 天仍有效"))
    return p


checklib.run(check)
