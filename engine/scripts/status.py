# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""OmniKit 本機優先狀態板引擎（免 GitHub 私人 repo 即可開箱使用 NOW.md 與交接，相容既有遠端狀態庫）。

設計要點（回應盲審 P0-3、P1-6、P1-7）：
1. 零帳號預設：~/.omnikit/status 不存在或無 .git 時，自動以 `git init -b main` 初始化本機狀態庫，
   並僅在 OmniKit 新初始化的本機庫設定 repo 層級固定身分（OmniKit <omnikit@localhost.invalid>）與
   `commit.gpgsign=false`，即使新電腦完全沒設全域 git 身分或開了 GPG 簽章也能穩定保留版本紀錄。
2. 零干擾相容：若 ~/.omnikit/status 原本已是綁定遠端的 git repo（例如維護者的私人狀態庫），不改任何 git config，
   自動識別為 `remote` 模式。
3. 邊界隔離：所有 git 呼叫明確指定 `--git-dir` 與 `--work-tree`，並設 `GIT_CEILING_DIRECTORIES`、
   `GIT_TERMINAL_PROMPT=0`、`GCM_INTERACTIVE=Never` 與 `stdin=DEVNULL`，絕不誤寫上層家目錄 repo、絕不彈憑證視窗。
4. 跨行程排他鎖：`~/.omnikit/locks/status.lock`（Windows 用 msvcrt.locking，POSIX 用 fcntl.flock）。

用法：
  uv run engine/scripts/status.py init [--json]
  uv run engine/scripts/status.py sync [--json]
  uv run engine/scripts/status.py path <專案代號> [--project-path <路徑>] [--ensure] [--json]
  uv run engine/scripts/status.py save [-m <訊息>] [--path <相對路徑>...] [--push] [--json]
  uv run engine/scripts/status.py history <專案代號> [--limit 10] [--json]
  uv run engine/scripts/status.py restore <專案代號> --rev <commit> [--json]
  uv run engine/scripts/status.py --selftest
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import statedir  # noqa: E402
from fsretry import retry  # noqa: E402

SAFE_PROJECT_ID = re.compile(r"^[\w.-]+$")
WIN_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
)
SAFE_REV = re.compile(r"^[0-9a-fA-F]{4,40}$")
GITATTRIBUTES = "* text=auto eol=lf\n*/handoffs/** merge=union\nhandoffs/** merge=union\n"
GITIGNORE = ".omnikit-tmp-*\n*.bak*\n"


def validate_project_id(project_id: str) -> str:
    pid = str(project_id or "").strip()
    if (
        not pid
        or pid.strip(".") == ""
        or pid.endswith((".", " "))
        or pid.split(".")[0].upper() in WIN_RESERVED
        or not SAFE_PROJECT_ID.match(pid)
    ):
        raise ValueError(f"不合法的專案代號：{project_id!r}（只允許中英數字、底線、點與連字號，且不可全為點號）")
    return pid


def status_dir(state: Path | None = None) -> Path:
    base = state if state is not None else statedir.state_dir()
    return base / "status"


@contextlib.contextmanager
def status_lock(state: Path):
    lock_file = state / "locks" / "status.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    if not lock_file.is_file() or lock_file.stat().st_size == 0:
        lock_file.write_bytes(b"0")
    f = open(lock_file, "r+b")
    try:
        f.seek(0)
        if os.name == "nt":
            import msvcrt

            for _ in range(100):
                try:
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    import time

                    time.sleep(0.05)
            else:
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                try:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        else:
            import fcntl

            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    finally:
        f.close()


def _git_env(sdir: Path, extra_env: dict[str, str] | None = None) -> dict[str, str]:
    base = dict(extra_env if extra_env is not None else os.environ)
    for k in list(base):
        if k.startswith("GIT_") and k not in ("GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL", "GIT_EXEC_PATH"):
            base.pop(k, None)
    base["GIT_CEILING_DIRECTORIES"] = str(sdir.parent.resolve())
    base["GIT_TERMINAL_PROMPT"] = "0"
    base["GCM_INTERACTIVE"] = "Never"
    return base


def _run_git(sdir: Path, args: list[str], *, timeout: int = 15, extra_env: dict[str, str] | None = None,
             use_git_dir: bool = True) -> tuple[int, str, str]:
    git_exe = shutil.which("git")
    if not git_exe:
        return 127, "", "找不到 git 執行檔"
    cmd = [git_exe, "-c", "core.longpaths=true"]
    if use_git_dir:
        # 使用相對於 cwd(sdir) 的 .git，避免 Windows 含中文長路徑超過 260 UTF-8 bytes 觸發 fatal: '$GIT_DIR' too big
        cmd.extend(["--git-dir=.git", "--work-tree=."])
    cmd.extend(args)
    kw: dict[str, Any] = {
        "cwd": str(sdir),
        "env": _git_env(sdir, extra_env),
        "stdin": subprocess.DEVNULL,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
    }
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(cmd, check=False, **kw)
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, "", str(exc)


def detect_mode(sdir: Path, *, extra_env: dict[str, str] | None = None) -> dict[str, Any]:
    git_dir = sdir / ".git"
    if not git_dir.exists():
        return {"initialized": False, "mode": "uninitialized", "remote": "", "stale_lock": False}
    lock_p = git_dir / "index.lock"
    stale_lock = False
    if lock_p.is_file():
        try:
            age_sec = datetime.now().timestamp() - lock_p.stat().st_mtime
            stale_lock = age_sec > 600
        except OSError:
            stale_lock = False
    rc, out, _ = _run_git(sdir, ["remote", "get-url", "origin"], extra_env=extra_env)
    remote = out.strip() if rc == 0 and out.strip() else ""
    return {
        "initialized": True,
        "mode": "remote" if remote else "local",
        "remote": remote,
        "stale_lock": stale_lock,
    }


def _write_text_lf(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    retry(path.write_bytes, content.replace("\r\n", "\n").encode("utf-8"))


def init_status(state: Path | None = None, *, extra_env: dict[str, str] | None = None) -> dict[str, Any]:
    base_state = state if state is not None else statedir.state_dir()
    sdir = status_dir(base_state)
    sdir.mkdir(parents=True, exist_ok=True)
    with status_lock(base_state):
        info = detect_mode(sdir, extra_env=extra_env)
        if info["initialized"]:
            return {"ok": True, "created": False, "dir": str(sdir), **info}

        if not shutil.which("git"):
            return {
                "ok": True,
                "created": False,
                "initialized": False,
                "mode": "plain",
                "remote": "",
                "dir": str(sdir),
                "note": "找不到 git，暫以純資料夾模式運作",
            }

        had_files = any(p.name not in (".gitattributes", ".gitignore") for p in sdir.iterdir())
        rc, _, err = _run_git(sdir, ["init", "-b", "main", "--template="], extra_env=extra_env, use_git_dir=False)
        if rc != 0:
            rc, _, err = _run_git(sdir, ["init", "--template="], extra_env=extra_env, use_git_dir=False)
            if rc == 0:
                _run_git(sdir, ["symbolic-ref", "HEAD", "refs/heads/main"], extra_env=extra_env)
        if rc != 0:
            return {"ok": False, "created": False, "initialized": False, "mode": "error", "dir": str(sdir), "error": err}

        # 只對 OmniKit 新建的本機庫設定 repo 層級固定身分與關簽章，絕不碰全域設定
        for k, v in (
            ("user.name", "OmniKit"),
            ("user.email", "omnikit@localhost.invalid"),
            ("commit.gpgsign", "false"),
            ("tag.gpgSign", "false"),
            ("core.autocrlf", "false"),
            ("core.longpaths", "true"),
        ):
            _run_git(sdir, ["config", "--local", k, v], extra_env=extra_env)

        if not (sdir / ".gitattributes").is_file():
            _write_text_lf(sdir / ".gitattributes", GITATTRIBUTES)
        if not (sdir / ".gitignore").is_file():
            _write_text_lf(sdir / ".gitignore", GITIGNORE)

        _run_git(sdir, ["add", "-A"], extra_env=extra_env)
        msg = "chore: 匯入既有本機狀態板" if had_files else "chore: 初始化本機狀態板"
        rc_c, _, err_c = _run_git(sdir, ["commit", "-m", msg], extra_env=extra_env)
        return {
            "ok": rc_c == 0,
            "created": True,
            "initialized": True,
            "mode": "local",
            "remote": "",
            "stale_lock": False,
            "dir": str(sdir),
            **({"error": err_c} if rc_c != 0 else {}),
        }


def sync_status(state: Path | None = None, *, extra_env: dict[str, str] | None = None) -> dict[str, Any]:
    base_state = state if state is not None else statedir.state_dir()
    sdir = status_dir(base_state)
    if not (sdir / ".git").exists():
        init_res = init_status(base_state, extra_env=extra_env)
        if not init_res.get("ok"):
            return {"ok": False, "synced": False, "mode": "error", "reason": init_res.get("error") or "初始化狀態板失敗"}
    with status_lock(base_state):
        info = detect_mode(sdir, extra_env=extra_env)
        if info["mode"] != "remote":
            return {
                "ok": True,
                "synced": True,
                "mode": info["mode"],
                "message": "本機狀態板就緒（免遠端帳號）",
                "stale_lock": info["stale_lock"],
            }
        rc, out, err = _run_git(sdir, ["pull", "--ff-only"], timeout=20, extra_env=extra_env)
        if rc == 0:
            return {"ok": True, "synced": True, "mode": "remote", "message": out or "已同步遠端狀態庫"}
        return {"ok": False, "synced": False, "mode": "remote", "reason": err or out or "git pull --ff-only 失敗"}


def initial_now_template(project_id: str, project_path: str = "") -> str:
    now_str = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    path_line = f"`{project_path}`" if project_path else "（本機專案）"
    return (
        f"# {project_id} 狀態板\n\n"
        f"- 更新時間：{now_str}\n"
        f"- 專案路徑：{path_line}\n\n"
        "## 完工路徑\n"
        "還有 1 步，完成 0 步（上坡）\n"
        "- [ ] 盤點需求與建立第一階段完工步驟\n\n"
        "## 目前結論\n"
        "- 已建立本機狀態板（零帳號免 GitHub，自動保留本機歷史紀錄）\n\n"
        "## 不滿意待改\n\n"
        "## 等使用者決定的事\n"
        "- 無\n\n"
        "## 下一步\n"
        "- 【agent 可直接做】開啟專案對話，對照程式碼與目標更新 NOW.md\n"
    )


def project_now_path(
    project_id: str,
    *,
    state: Path | None = None,
    project_path: str = "",
    ensure: bool = False,
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    base_state = state if state is not None else statedir.state_dir()
    pid = validate_project_id(project_id)
    sdir = status_dir(base_state)
    sdir.mkdir(parents=True, exist_ok=True)
    base_resolved = sdir.resolve()
    target = (sdir / pid / "NOW.md").resolve()
    if base_resolved not in target.parents:
        raise ValueError("不合法的狀態板路徑")
    created = False
    if ensure and not target.is_file():
        init_status(base_state, extra_env=extra_env)
        _write_text_lf(target, initial_now_template(pid, project_path=project_path))
        save_status(
            state=base_state,
            message=f"status({pid}): 建立初始 NOW.md",
            rel_paths=[f"{pid}/NOW.md"],
            extra_env=extra_env,
        )
        created = True
    return {"ok": True, "project_id": pid, "path": str(target), "exists": target.is_file(), "created": created}


def save_status(
    *,
    state: Path | None = None,
    message: str = "status: 更新狀態板",
    rel_paths: list[str] | None = None,
    push: bool = False,
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    base_state = state if state is not None else statedir.state_dir()
    sdir = status_dir(base_state)
    if not (sdir / ".git").exists():
        init_res = init_status(base_state, extra_env=extra_env)
        if not init_res.get("initialized"):
            return {"ok": True, "committed": False, "pushed": False, "mode": "plain", "note": "已寫入本機檔案（環境無 git）"}

    with status_lock(base_state):
        info = detect_mode(sdir, extra_env=extra_env)
        if info["stale_lock"]:
            return {
                "ok": False,
                "committed": False,
                "pushed": False,
                "mode": info["mode"],
                "note": f"狀態板鎖定檔殘留（{sdir / '.git' / 'index.lock'}），請確認無 git 執行後移除該鎖檔",
            }
        add_args = ["add", "--", *rel_paths] if rel_paths else ["add", "-A"]
        rc_add, _, err_add = _run_git(sdir, add_args, extra_env=extra_env)
        if rc_add != 0:
            return {"ok": False, "committed": False, "pushed": False, "mode": info["mode"], "note": f"git add 失敗：{err_add}"}

        diff_args = ["diff", "--cached", "--quiet", "--", *(rel_paths or [])]
        rc_diff, _, _ = _run_git(sdir, diff_args, extra_env=extra_env)
        if rc_diff == 0:
            return {"ok": True, "committed": False, "pushed": False, "mode": info["mode"], "note": "內容無變更，無須新增歷史紀錄"}

        commit_args = ["commit", "-m", message]
        if rel_paths:
            commit_args.extend(["--", *rel_paths])
        rc_c, _, err_c = _run_git(sdir, commit_args, extra_env=extra_env)
        if rc_c != 0:
            # 萬一舊有本機 repo 還沒設身分導致失敗，當僅為 local 模式時自動補上 repo 級預設身分重試一次
            if info["mode"] == "local" and ("identity unknown" in err_c.lower() or "please tell me who you are" in err_c.lower()):
                _run_git(sdir, ["config", "--local", "user.name", "OmniKit"], extra_env=extra_env)
                _run_git(sdir, ["config", "--local", "user.email", "omnikit@localhost.invalid"], extra_env=extra_env)
                _run_git(sdir, ["config", "--local", "commit.gpgsign", "false"], extra_env=extra_env)
                rc_c, _, err_c = _run_git(sdir, commit_args, extra_env=extra_env)
            if rc_c != 0:
                return {
                    "ok": False,
                    "committed": False,
                    "pushed": False,
                    "mode": info["mode"],
                    "note": f"已寫入檔案，但建立本機歷史紀錄失敗：{err_c}",
                }

        pushed = False
        note = "已儲存並記錄本機版本歷史"
        if push and info["mode"] == "remote":
            rc_rb, _, err_rb = _run_git(sdir, ["pull", "--rebase"], timeout=20, extra_env=extra_env)
            if rc_rb != 0:
                _run_git(sdir, ["rebase", "--abort"], timeout=10, extra_env=extra_env)
                note = f"已記錄本機歷史，但遠端同步衝突已自動中止 rebase（未推送）：{err_rb}"
            else:
                rc_p, _, err_p = _run_git(sdir, ["push"], timeout=20, extra_env=extra_env)
                if rc_p == 0:
                    pushed = True
                    note = "已儲存並同步至遠端狀態庫"
                else:
                    note = f"已記錄本機歷史，但遠端推送未完成：{err_p}"
        return {"ok": True, "committed": True, "pushed": pushed, "mode": info["mode"], "note": note}


def bind_remote(remote_url: str, *, state: Path | None = None, extra_env: dict[str, str] | None = None) -> dict[str, Any]:
    """將已初始化的本機 ~/.omnikit/status 無縫綁定至遠端私人儲存庫（不需手動刪資料夾再 clone）。"""
    url = str(remote_url or "").strip()
    if not url:
        raise ValueError("請提供遠端 Git 儲存庫網址")
    base_state = state if state is not None else statedir.state_dir()
    init_status(base_state, extra_env=extra_env)
    sdir = status_dir(base_state)
    with status_lock(base_state):
        rc_get, _, _ = _run_git(sdir, ["remote", "get-url", "origin"], extra_env=extra_env)
        if rc_get == 0:
            rc, _, err = _run_git(sdir, ["remote", "set-url", "origin", url], extra_env=extra_env)
        else:
            rc, _, err = _run_git(sdir, ["remote", "add", "origin", url], extra_env=extra_env)
        if rc != 0:
            return {"ok": False, "error": err or "設定遠端 origin 失敗"}
        return {"ok": True, "mode": "remote", "remote": url, "note": f"已綁定遠端狀態庫：{url}（可執行 status.py save --push 同步）"}


def project_history(
    project_id: str,
    *,
    state: Path | None = None,
    limit: int = 12,
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    base_state = state if state is not None else statedir.state_dir()
    pid = validate_project_id(project_id)
    sdir = status_dir(base_state)
    if not (sdir / ".git").exists():
        return {"ok": True, "project_id": pid, "entries": []}
    n = max(1, min(50, int(limit)))
    rc, out, _ = _run_git(
        sdir,
        ["log", f"-n{n}", "--format=%h%x1f%cI%x1f%s", "--", f"{pid}/NOW.md"],
        extra_env=extra_env,
    )
    entries = []
    if rc == 0 and out:
        for line in out.splitlines():
            parts = line.split("\x1f")
            if len(parts) >= 3:
                entries.append({"rev": parts[0].strip(), "at": parts[1].strip(), "summary": parts[2].strip()})
    return {"ok": True, "project_id": pid, "entries": entries}


def restore_project_now(
    project_id: str,
    rev: str,
    *,
    state: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    base_state = state if state is not None else statedir.state_dir()
    pid = validate_project_id(project_id)
    clean_rev = str(rev or "").strip()
    if not SAFE_REV.match(clean_rev):
        raise ValueError("不合法的版本代號")
    sdir = status_dir(base_state)
    if not (sdir / ".git").exists():
        raise FileNotFoundError("此狀態板尚未建立版本紀錄")
    rel = f"{pid}/NOW.md"
    rc, content, err = _run_git(sdir, ["show", f"{clean_rev}:{rel}"], extra_env=extra_env)
    if rc != 0:
        raise ValueError(f"找不到指定版本的狀態板內容：{err}")
    target = (sdir / pid / "NOW.md").resolve()
    _write_text_lf(target, content + ("\n" if not content.endswith("\n") else ""))
    save_res = save_status(
        state=base_state,
        message=f"status({pid}): 還原至版本 {clean_rev[:7]}",
        rel_paths=[rel],
        extra_env=extra_env,
    )
    return {"ok": True, "project_id": pid, "restored_from": clean_rev, "save": save_res}


def selftest() -> int:
    fails: list[str] = []

    def check(label: str, cond: bool, detail: str = "") -> None:
        print(f"{'通過' if cond else '失敗'}：{label}" + (f"（{detail}）" if detail else ""))
        if not cond:
            fails.append(label)

    with tempfile.TemporaryDirectory(prefix="ok-st-") as tmp:
        root = Path(tmp)
        empty_global = root / "empty.gitconfig"
        empty_global.write_text("[commit]\n\tgpgsign = true\n", encoding="utf-8")
        isolated_env = {
            **os.environ,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": str(empty_global),
            "EMAIL": "",
        }
        for k in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
            isolated_env.pop(k, None)

        # 1. 上層目錄本身是 git repo 時，init/save 絕不污染上層 repo，且無全域 git 身分＋全域開 gpgsign 仍 100% 成功
        outer = root / "outer_home"
        outer.mkdir()
        subprocess.run(["git", "init", "--quiet"], cwd=str(outer), check=True)
        state = outer / ".omnikit"

        r_init = init_status(state, extra_env=isolated_env)
        check("無全域 git 身分＋全域 gpgsign=true 下 init -b main 成功",
              r_init["ok"] is True and r_init["mode"] == "local" and (state / "status" / ".git").is_dir(),
              str(r_init))
        _, br, _ = _run_git(state / "status", ["branch", "--show-current"], extra_env=isolated_env)
        check("預設分支固定為 main（避免日後綁 GitHub 時 master/main 分裂）", br == "main", br)

        r_path = project_now_path("DemoApp", state=state, project_path=r"C:\dev\DemoApp", ensure=True, extra_env=isolated_env)
        now_f = Path(r_path["path"])
        check("path --ensure 自動建立初始 NOW.md 並寫入首筆歷史", r_path["created"] is True and now_f.is_file())

        _write_text_lf(now_f, now_f.read_text("utf-8") + "\n- 新增結論測試\n")
        r_save = save_status(state=state, message="status(DemoApp): 第二版", rel_paths=["DemoApp/NOW.md"], extra_env=isolated_env)
        check("無全域身分下 save 成功 commit", r_save["ok"] is True and r_save["committed"] is True, str(r_save))

        r_sync = sync_status(state, extra_env=isolated_env)
        check("本機模式 sync 直接成功、不跑 git pull 報錯", r_sync["ok"] is True and r_sync["synced"] is True and r_sync["mode"] == "local")

        hist = project_history("DemoApp", state=state, extra_env=isolated_env)
        check("history 可讀出 2 筆本機歷史紀錄", len(hist["entries"]) == 2, str(hist["entries"]))

        first_rev = hist["entries"][-1]["rev"]
        r_rest = restore_project_now("DemoApp", first_rev, state=state, extra_env=isolated_env)
        check("restore 一鍵還原回舊版內容並留存新紀錄",
              r_rest["ok"] is True and "新增結論測試" not in now_f.read_text("utf-8"))

        # 確認既有遠端狀態庫不會被改動設定
        rem_state = root / "remote_state"
        rem_sdir = rem_state / "status"
        rem_sdir.mkdir(parents=True)
        subprocess.run(["git", "init", "--quiet"], cwd=str(rem_sdir), check=True)
        subprocess.run(["git", "config", "--local", "user.email", "me@private.example"], cwd=str(rem_sdir), check=True)
        subprocess.run(["git", "remote", "add", "origin", "https://example.com/me/status.git"], cwd=str(rem_sdir), check=True)
        r_rem = init_status(rem_state, extra_env=isolated_env)
        _, kept_email, _ = _run_git(rem_sdir, ["config", "--local", "--get", "user.email"], extra_env=isolated_env)
        check("既有遠端狀態庫識別為 remote 且完全保留使用者原 git 設定",
              r_rem["mode"] == "remote" and r_rem["created"] is False and kept_email == "me@private.example")

        # 路徑穿越防禦
        blocked = False
        try:
            project_now_path("../evil", state=state)
        except ValueError:
            blocked = True
        check("拒絕路徑穿越專案代號", blocked)

    print(f"\n{'status.py selftest：全部通過' if not fails else f'status.py selftest：{len(fails)} 項失敗'}")
    return 1 if fails else 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="OmniKit 本機優先狀態板管理工具")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--state-dir", type=Path, default=None)
    sub = parser.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", help="初始化本機狀態板目錄與版本紀錄")
    p_init.add_argument("--json", action="store_true")

    p_sync = sub.add_parser("sync", help="同步狀態板（本機模式免遠端直接就緒；遠端模式安全快轉）")
    p_sync.add_argument("--json", action="store_true")

    p_path = sub.add_parser("path", help="取得指定專案的 NOW.md 路徑（可選 --ensure 自動建立）")
    p_path.add_argument("project_id")
    p_path.add_argument("--project-path", default="")
    p_path.add_argument("--ensure", action="store_true")
    p_path.add_argument("--json", action="store_true")

    p_save = sub.add_parser("save", help="儲存狀態板變更至本機歷史（選配 --push 推送遠端）")
    p_save.add_argument("-m", "--message", default="status: 更新狀態板")
    p_save.add_argument("--path", dest="paths", action="append", default=None)
    p_save.add_argument("--push", action="store_true")
    p_save.add_argument("--json", action="store_true")

    p_hist = sub.add_parser("history", help="列出專案狀態板本機歷史版本")
    p_hist.add_argument("project_id")
    p_hist.add_argument("--limit", type=int, default=12)
    p_hist.add_argument("--json", action="store_true")

    p_rest = sub.add_parser("restore", help="還原專案狀態板至指定歷史版本")
    p_rest.add_argument("project_id")
    p_rest.add_argument("--rev", required=True)
    p_rest.add_argument("--json", action="store_true")

    p_rem = sub.add_parser("bind-remote", help="將既有本機狀態板綁定至遠端私人 Git 儲存庫")
    p_rem.add_argument("url")
    p_rem.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()

    st = args.state_dir
    if args.cmd == "init":
        res = init_status(st)
    elif args.cmd == "sync":
        res = sync_status(st)
    elif args.cmd == "path":
        res = project_now_path(args.project_id, state=st, project_path=args.project_path, ensure=args.ensure)
        if not args.json:
            print(res["path"])
            return 0
    elif args.cmd == "save":
        res = save_status(state=st, message=args.message, rel_paths=args.paths, push=args.push)
    elif args.cmd == "history":
        res = project_history(args.project_id, state=st, limit=args.limit)
    elif args.cmd == "restore":
        res = restore_project_now(args.project_id, args.rev, state=st)
    elif args.cmd == "bind-remote":
        res = bind_remote(args.url, state=st)
    else:
        parser.print_help()
        return 2

    if getattr(args, "json", False):
        print(json.dumps(res, ensure_ascii=False))
    else:
        msg = res.get("note") or res.get("message") or res.get("reason") or res.get("error") or json.dumps(res, ensure_ascii=False)
        print(msg)
    return 0 if res.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
