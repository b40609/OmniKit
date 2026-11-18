"""登入工作階段：建立、檢查、有活動時延長。時間都用秒（time.time()）。"""
import time

SESSION_SECONDS = 8 * 60 * 60
REMEMBER_SECONDS = 30 * 24 * 60 * 60


def now():
    return time.time()


def lifetime(remember):
    return REMEMBER_SECONDS if remember else SESSION_SECONDS


def create_session(user_id, remember=False, at=None):
    at = now() if at is None else at
    return {"user": user_id, "created": at, "remember": remember, "expires": at + lifetime(remember)}


def is_valid(session, at=None):
    at = now() if at is None else at
    return at < session["expires"]


def touch(session, at=None):
    at = now() if at is None else at
    session["expires"] = at + lifetime(session["remember"])
    return session
