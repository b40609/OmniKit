"""每個請求都會經過這裡。"""
from .session import is_valid, touch


def handle_request(session, at=None):
    if not is_valid(session, at):
        return {"status": 401, "redirect": "/login"}
    touch(session, at)
    return {"status": 200}
