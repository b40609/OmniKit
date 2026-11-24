"""OmniKit 個人面板背景自動對帳佇列。

設計原則：
1. 遵守 visibility: visible：一律透過 `t3 thread start` 開在 T3 看得到的對話，使用者隨時可點進去看 prompt 與過程。
2. 遵守 Google 帳號低並行建議：單一 FIFO worker 執行緒，一次只跑一條對帳對話，絕不併發轟炸。
3. 遵守 Gemini 思考程度定案：固定使用 `--provider antigravity_ryan --model gemini-4-hydrogen --option thought_level=xhigh`
   （可由參數覆寫，供測試或個人設定調整）。
4. 零盲讀千項長對話：先由本機 Python 精準擷取近期 Git commit、dirty 檔、最近對話的最後數則訊息與舊 NOW.md，
   透過 stdin 傳入，省時省額度、不遺失使用者已記下的「不滿意待改」條目。
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from . import collector

DEFAULT_PROVIDER = "antigravity_ryan"
DEFAULT_MODEL = "gemini-4-hydrogen"
DEFAULT_OPTION = "thought_level=xhigh"
RECONCILE_TIMEOUT_SEC = 300


def _collect_git_context(project_path: Path) -> str:
    if not project_path.is_dir():
        return "（本機無此目錄）"
    rc_log, log_out, _ = collector._run_cmd(
        ["git", "log", "-n", "12", "--date=short", "--format=%h %ad %s"],
        cwd=project_path,
        timeout=6,
    )
    _, st_out, _ = collector._run_cmd(["git", "status", "--short"], cwd=project_path, timeout=6)
    _, br_out, _ = collector._run_cmd(["git", "branch", "--show-current"], cwd=project_path, timeout=5)
    branch = br_out.strip() or "(detached)"
    log_block = log_out.strip() if rc_log == 0 and log_out.strip() else "（無 commit 紀錄）"
    dirty_lines = [ln for ln in st_out.splitlines() if ln.strip()]
    dirty_block = "\n".join(dirty_lines[:20]) if dirty_lines else "（工作樹乾淨）"
    if len(dirty_lines) > 20:
        dirty_block += f"\n...（其餘 {len(dirty_lines) - 20} 檔略）"
    return f"目前分支：{branch}\n\n最近 commit（新到舊）：\n{log_block}\n\n尚未提交變更：\n{dirty_block}"


def _collect_recent_t3_context(project_path: Path) -> str:
    cli = collector._find_t3_cli()
    if not cli or not project_path.is_dir():
        return "（找不到 t3 CLI 或本機目錄）"
    rc, out, _ = collector._run_cmd([cli, "thread", "list", "--project", str(project_path), "--json"], timeout=10)
    if rc != 0:
        return "（讀取 T3 對話清單失敗）"
    try:
        threads = json.loads(out)
    except ValueError:
        return "（T3 回傳非合法 JSON）"
    if not isinstance(threads, list):
        return "（無 T3 對話）"

    active = [t for t in threads if isinstance(t, dict) and not t.get("settled") and not t.get("archived")]
    active.sort(key=lambda t: str(t.get("updatedAt") or ""), reverse=True)
    if not active:
        return "（目前沒有未結案的 T3 對話）"

    snippets: list[str] = []
    for th in active[:3]:
        tid = str(th.get("threadId") or "")
        title = str(th.get("title") or "未命名")
        status = str(th.get("status") or "")
        items = int(th.get("itemCount") or 0)
        head = f"- 對話「{title}」（id: {tid}，狀態: {status}，items: {items}）"
        rc_s, show_out, _ = collector._run_cmd([cli, "thread", "show", tid, "--messages", "4"], timeout=10)
        if rc_s == 0 and show_out.strip():
            trimmed = show_out.strip()
            if len(trimmed) > 1400:
                trimmed = trimmed[-1400:]
            head += "\n  最近訊息節錄：\n  " + trimmed.replace("\n", "\n  ")
        snippets.append(head)
    return "\n\n".join(snippets)


def build_reconcile_prompt(
    project_id: str,
    project_name: str,
    project_path: Path,
    now_path: Path,
    *,
    git_ctx: str,
    t3_ctx: str,
    old_now: str,
) -> str:
    now_stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    old_block = old_now.strip() if old_now.strip() else "（目前尚未建立 NOW.md）"
    if len(old_block) > 4000:
        old_block = old_block[:4000] + "\n...（其餘略）"

    return f"""你是 OmniKit 個人面板派出的自動對帳助手，請依據下方本機實測資料，幫專案「{project_name}」更新狀態板檔案：
目標檔案：`{now_path}`

請嚴格遵守以下要求（只更新狀態板，不要修改專案程式碼）：
1. 確保目標檔案開頭包含：
   - 更新時間：{now_stamp}
   - 專案路徑：`{project_path}`
   - 分支與主線對話（若有）
2. 照 `omnikit-handoff` 四格契約整理清楚、精簡、無廢話（繁體中文、嚴禁 LaTeX 語法）：
   - `## 完工路徑`：第一行寫明「還有 N 步，完成 M 步（上坡／下坡）」，列出本階段關鍵可驗證步驟（`- [x]` / `- [ ]`）。
   - `## 目前結論`：只留最新生效的 1 到 3 條拍板定案，新蓋舊。
   - `## 不滿意待改`：**務必完整保留原本未勾選 `- [ ]` 與已勾選 `- [x]` 的所有不滿意待改條目，絕對不要誤刪！** 若原本沒有，寫 `- 無`。
   - `## 等使用者決定的事`：只列目前真的卡在使用者身上待拍板的項目（無則寫 `- 無`）。
   - `## 下一步`：第一條放目前唯一沒有被擋住的最優先動作，明確標記 `【等使用者】` 或 `【agent 可直接做】`。
3. 寫檔完成後，若 `{now_path.parent.parent}` 是 git repo，請只針對 `{project_id}/NOW.md` 做 `git add` 與 `git commit`（不強制 push）。
4. 若你具備 `t3_thread_organize` 工具，輸出精簡 3 行回報後，請主動呼叫 `t3_thread_organize(action="settle")` 結案本子對話。

---
### 專案客觀 Git 狀態
{git_ctx}

---
### 專案近期 T3 對話節錄
{t3_ctx}

---
### 原本的 NOW.md 內容
{old_block}
"""


def run_t3_reconcile(
    *,
    project_id: str,
    project_name: str,
    project_path: Path,
    now_path: Path,
    t3_base_url: str = "",
    provider: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    option: str = DEFAULT_OPTION,
) -> dict[str, Any]:
    """預設執行器：呼叫官方 `t3 thread start` 開可見對話完成對帳。"""
    cli = collector._find_t3_cli()
    if not cli:
        raise RuntimeError("找不到本機 t3 CLI，無法自動派送對帳對話")
    if not project_path.is_dir():
        raise RuntimeError(f"本機找不到專案目錄：{project_path}")

    git_ctx = _collect_git_context(project_path)
    t3_ctx = _collect_recent_t3_context(project_path)
    old_now = collector.read_utf8(now_path) if now_path.is_file() else ""
    prompt = build_reconcile_prompt(
        project_id,
        project_name,
        project_path,
        now_path,
        git_ctx=git_ctx,
        t3_ctx=t3_ctx,
        old_now=old_now,
    )

    cmd = [
        cli,
        "thread",
        "start",
        str(project_path),
        "-",
        "--title",
        f"[Cockpit 自動對帳] {project_name} NOW.md",
        "--provider",
        provider,
        "--model",
        model,
        "--option",
        option,
        "--wait",
        "--json",
    ]
    kwargs: dict[str, Any] = {
        "input": prompt,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": RECONCILE_TIMEOUT_SEC,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    proc = subprocess.run(cmd, check=False, **kwargs)
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()

    thread_id = ""
    thread_url = ""
    if out:
        try:
            doc = json.loads(out)
            if isinstance(doc, dict):
                thread_id = str(doc.get("threadId") or doc.get("id") or "")
                raw_link = str(doc.get("link") or "")
                thread_url = collector.rewrite_t3_link(raw_link, t3_base_url) if raw_link else ""
        except ValueError:
            pass

    if proc.returncode != 0:
        detail = collector.sanitize(err or out or f"t3 thread start 結束碼 {proc.returncode}")
        raise RuntimeError(detail)

    return {
        "thread_id": thread_id,
        "thread_url": thread_url,
        "message": f"{project_name} 已自動對帳更新 NOW.md",
    }


class ReconcileManager:
    """單一 FIFO 背景對帳排程器（一次一條，避免多開併發）。"""

    def __init__(
        self,
        *,
        state_dir: Path,
        on_done: Callable[[], None] | None = None,
        runner: Callable[..., dict[str, Any]] | None = None,
    ):
        self.state_dir = state_dir
        self.on_done = on_done
        self.runner = runner if runner is not None else run_t3_reconcile
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._worker: threading.Thread | None = None

    def _ensure_worker(self) -> None:
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._loop, name="cockpit-reconciler", daemon=True)
            self._worker.start()

    def enqueue(self, project: dict[str, Any], *, t3_base_url: str = "") -> dict[str, Any]:
        pid = collector.validate_project_id(str(project["id"]))
        if project.get("remote_only") or not project.get("path"):
            raise ValueError(f"專案 {pid} 為遠端專案（本機無目錄），請在所屬電腦執行對帳")

        with self._lock:
            existing = self._jobs.get(pid)
            if existing and existing["status"] in ("queued", "running"):
                return dict(existing)

            job = {
                "project_id": pid,
                "project_name": str(project.get("name") or pid),
                "project_path": str(project["path"]),
                "t3_base_url": t3_base_url,
                "status": "queued",
                "queued_at": collector.iso_utc(collector.utc_now()),
                "started_at": None,
                "finished_at": None,
                "thread_id": "",
                "thread_url": "",
                "message": "已排入對帳佇列，等待執行…",
                "error": "",
            }
            self._jobs[pid] = job
            self._queue.put(job)
            self._ensure_worker()
            return dict(job)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            jobs_copy = {pid: {k: v for k, v in j.items() if k not in ("project_path", "t3_base_url")} for pid, j in self._jobs.items()}
        active = [j for j in jobs_copy.values() if j["status"] in ("queued", "running")]
        running = next((j["project_id"] for j in active if j["status"] == "running"), None)
        return {
            "busy": bool(active),
            "active_count": len(active),
            "running_project": running,
            "jobs": jobs_copy,
        }

    def _loop(self) -> None:
        while True:
            try:
                job = self._queue.get(timeout=5.0)
            except queue.Empty:
                continue

            pid = job["project_id"]
            with self._lock:
                job["status"] = "running"
                job["started_at"] = collector.iso_utc(collector.utc_now())
                job["message"] = "正在透過 T3（Hydrogen xhigh）讀取 Git 與對話並更新 NOW.md…"
                job["error"] = ""

            try:
                now_path = collector.safe_status_now_path(self.state_dir, pid)
                res = self.runner(
                    project_id=pid,
                    project_name=job["project_name"],
                    project_path=Path(job["project_path"]),
                    now_path=now_path,
                    t3_base_url=job["t3_base_url"],
                )
                with self._lock:
                    job["status"] = "done"
                    job["finished_at"] = collector.iso_utc(collector.utc_now())
                    job["thread_id"] = str(res.get("thread_id") or "")
                    job["thread_url"] = str(res.get("thread_url") or "")
                    job["message"] = str(res.get("message") or "已完成自動對帳")
            except Exception as exc:  # noqa: BLE001  單一任務失敗不可弄掛背景佇列
                with self._lock:
                    job["status"] = "error"
                    job["finished_at"] = collector.iso_utc(collector.utc_now())
                    job["error"] = collector.sanitize(exc)
                    job["message"] = f"對帳失敗：{job['error']}"
            finally:
                if self.on_done is not None:
                    try:
                        self.on_done()
                    except Exception as exc:  # noqa: BLE001
                        import sys

                        sys.stderr.write(f"[cockpit] reconcile callback error: {collector.sanitize(exc)}\n")
                self._queue.task_done()
