"""登入工作階段：建立、檢查、有活動時延長。時間都用秒（time.time()）。"""
import time

SESSION_MINUTES = 480  # 一般登入 8 小時
REMEMBER_DAYS = 30


def now():
    return time.time()


def create_session(user_id, remember=False, at=None):
    at = now() if at is None else at
    if remember:
        expires = at + REMEMBER_DAYS * 24 * 60 * 60 * 1000
    else:
        expires = at + SESSION_MINUTES * 60
    return {"user": user_id, "created": at, "remember": remember, "expires": expires}


def is_valid(session, at=None):
    at = now() if at is None else at
    return at < session["expires"]


def touch(session, at=None):
    """使用者有操作時呼叫：把到期時間往後延。"""
    at = now() if at is None else at
    if session["remember"]:
        session["expires"] = at + REMEMBER_DAYS * 24 * 60
    else:
        session["expires"] = at + SESSION_MINUTES
    return session
