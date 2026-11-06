# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""防毒短暫鎖住檔案時重試（FR-34）。

公司電腦的防毒（例如 Trend Micro）會在檔案剛寫好、剛複製好時掃描它；掃描的那一兩秒，別的程式打不開、
改不了也刪不掉，Windows 回報 winerror 32（檔案正由另一個程序使用）或 5（存取被拒），Python 是 PermissionError。
寫檔、複製、刪除、改名遇到這種錯誤就等一下再試，每次等久一點；試完還是被鎖住，才把原本的錯誤丟出去，
並在錯誤上加註原因。找不到檔案、磁碟滿了這類錯誤不重試。

用法：
  from fsretry import retry
  retry(path.write_bytes, data)      跟 path.write_bytes(data) 一樣，只是被鎖住時會等一下再試

  uv run engine/scripts/fsretry.py --selftest
"""
import argparse
import errno
import os
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

# 每次被鎖住之後等幾秒再試；都試完還是被鎖住就放棄（總共最多等 3.75 秒）
DELAYS = (0.25, 0.5, 1.0, 2.0)
# 檔案被鎖住時 Windows 回報的錯誤：存取被拒、檔案正由另一個程序使用、檔案有一部分被鎖住
LOCKED = (5, 32, 33)
sleep = time.sleep  # 自我測試換成只記秒數，不真的等
_MISSING = object()


def locked(error):
    """是不是檔案被鎖住的錯誤：PermissionError，或 Windows 的 winerror 5、32、33。"""
    return isinstance(error, PermissionError) or getattr(error, "winerror", None) in LOCKED


def retry(fn, *args, **kwargs):
    """執行 fn(*args, **kwargs) 並回傳結果。檔案被鎖住就照 DELAYS 等一下再試，都試完還是被鎖住才丟出最後一次的錯誤；
    其他錯誤馬上丟出。fn 要能整個重做：失敗時沒寫完的部分，下一次會重寫。"""
    for delay in (*DELAYS, None):
        try:
            return fn(*args, **kwargs)
        except OSError as e:
            if not locked(e):
                raise
            if delay is None:
                e.add_note(f"OmniKit：重試 {len(DELAYS)} 次（共等 {sum(DELAYS):g} 秒）還是被鎖住，多半是防毒在掃描；"
                           "等一下再重跑一次")
                raise
            sleep(delay)


# ---- 自我測試用（其他腳本的 --selftest 也用） ----

@contextmanager
def flaky(owner, name, times=2, match=None):
    """把 owner.name（模組的函式或類別的方法）換掉：前 times 次（只算 match 為真的呼叫）丟出 Windows 鎖檔時的錯誤
    （PermissionError，winerror 32），之後照常執行；同時把重試的等待換成只記秒數。結束後換回原本的。
    yield 一個物件：calls 是算進去的呼叫次數，waits 是等了哪些秒數。"""
    global sleep
    real = getattr(owner, name)
    saved = vars(owner).get(name, _MISSING)
    stats = SimpleNamespace(calls=0, waits=[])

    def fake(*args, **kwargs):
        if match is None or match(*args, **kwargs):
            stats.calls += 1
            if stats.calls <= times:
                raise PermissionError(errno.EACCES, "檔案正由另一個程序使用（自我測試模擬防毒鎖檔）", None, 32)
        return real(*args, **kwargs)

    old_sleep, sleep = sleep, stats.waits.append
    setattr(owner, name, fake)
    try:
        yield stats
    finally:
        sleep = old_sleep
        if saved is _MISSING:
            delattr(owner, name)
        else:
            setattr(owner, name, saved)


def hold(path, seconds):
    """只有 Windows：用不分享的方式開著 path，seconds 秒後才放開；這段時間別的程式打不開、改不了也刪不掉
    （winerror 32），跟防毒掃描時一樣。回傳放開檔案的計時器。"""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                     wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    # GENERIC_READ、不跟別人分享（0）、OPEN_EXISTING、FILE_ATTRIBUTE_NORMAL
    handle = kernel32.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)
    if handle is None or handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    timer = threading.Timer(seconds, kernel32.CloseHandle, (handle,))
    timer.start()
    return timer


def selftest():
    failures = []

    def check(label, ok):
        print(f"{'通過' if ok else '失敗'}：{label}")
        if not ok:
            failures.append(label)

    def error_of(fn):
        try:
            fn()
        except OSError as e:
            return e
        return None

    box = SimpleNamespace(op=lambda: "ok")
    with flaky(box, "op", times=2) as st:
        result = retry(box.op)
    check("被鎖住兩次：每次等久一點（0.25、0.5 秒），第三次成功", result == "ok" and st.calls == 3 and st.waits == [0.25, 0.5])
    check("結束後換回原本的函式", box.op() == "ok")

    with flaky(box, "op", times=99) as st:
        e = error_of(lambda: retry(box.op))
    check("一直被鎖住：試 5 次、等 4 次之後丟出原本的錯誤，加註原因",
          isinstance(e, PermissionError) and st.calls == 5 and st.waits == list(DELAYS)
          and any("多半是防毒在掃描" in note for note in getattr(e, "__notes__", [])))

    def missing():
        raise FileNotFoundError(errno.ENOENT, "找不到")

    box.op = missing
    with flaky(box, "op", times=0) as st:
        e = error_of(lambda: retry(box.op))
    check("其他錯誤（找不到檔案）不重試，馬上丟出", isinstance(e, FileNotFoundError) and st.calls == 1 and st.waits == [])

    check("鎖檔的錯誤：PermissionError 算；找不到檔案、磁碟滿了不算",
          locked(PermissionError(errno.EACCES, "x")) and not locked(FileNotFoundError(errno.ENOENT, "x"))
          and not locked(OSError(errno.ENOSPC, "x")))
    if os.name == "nt":
        check("Windows：winerror 5、32、33 都算鎖檔，winerror 2（找不到檔案）不算",
              all(locked(OSError(errno.EINVAL, "x", None, w)) for w in LOCKED)
              and not locked(OSError(errno.EINVAL, "x", None, 2)))

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "王 小明 的 設定.json"
        with flaky(Path, "write_bytes", times=2, match=lambda p, *_: p == target) as st:
            retry(target.write_bytes, b"new")
            (Path(tmp) / "other.txt").write_bytes(b"x")  # match 不成立的照常寫，不算次數
        check("換掉 Path.write_bytes：只有指定的檔案被鎖住兩次，重試後寫進去",
              target.read_bytes() == b"new" and st.calls == 3 and (Path(tmp) / "other.txt").read_bytes() == b"x")
        target.write_bytes(b"after")
        check("結束後 Path.write_bytes 換回原本的", target.read_bytes() == b"after")

        if os.name == "nt":
            # 真的鎖住：用不分享的方式開著檔案 0.6 秒，跟防毒掃描時一樣
            timer = hold(target, 0.6)
            try:
                written = error_of(lambda: target.write_bytes(b"locked"))
                deleted = error_of(target.unlink)
                started = time.monotonic()
                retry(target.write_bytes, b"done")
                waited = time.monotonic() - started
            finally:
                timer.join()
            # open() 經過 C runtime，只剩 errno 13、沒有 winerror；刪除、改名直接呼叫 Windows，帶 winerror 32
            check("Windows 真的鎖住檔案：寫入與刪除都失敗（PermissionError，刪除帶 winerror 32），都算鎖檔",
                  isinstance(written, PermissionError) and isinstance(deleted, PermissionError)
                  and getattr(deleted, "winerror", None) == 32 and locked(written) and locked(deleted))
            check("Windows 真的鎖住檔案：重試等到放開之後寫進去", target.read_bytes() == b"done" and waited >= 0.2)
        else:
            print("略過：不是 Windows，沒有真的鎖住檔案")

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="防毒短暫鎖住檔案時重試（給其他腳本 import）")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
