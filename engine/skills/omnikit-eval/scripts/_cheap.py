"""便宜模型的非互動呼叫（第 1 層、證據卡整理用），回傳結構化 JSON 與 token 用量。

- Claude（預設）：claude -p --model haiku --output-format json --json-schema ... --tools "" --setting-sources ""
  --no-session-persistence。沒有任何工具可用、不載入使用者的 plugin 與 hook；在使用者資料夾外的中性目錄執行，
  不會讀到任何專案的 CLAUDE.md。README 這類外部內容只當資料，模型就算被誘導也做不了事。
  2026-11-05 實測：Haiku 一次約 4K token context、輸出在 structured_output。
- Codex：codex exec --json --output-schema <檔案> --sandbox read-only --ephemeral --skip-git-repo-check，
  prompt 從 stdin 給。

金鑰只靠各 CLI 自己的登入，這裡不讀不傳。便宜模型的結果只用來排除與排序，不能拿來決定勝負（FR-25）。
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

DEFAULT_MODEL = {"claude": "haiku", "codex": None}


def neutral_dir():
    """使用者資料夾外的空目錄：Claude 會往上找 CLAUDE.md，放在 C:\\Users\\<你> 底下會讀到 ~/.claude/CLAUDE.md。"""
    root = Path(os.environ.get("OMNIKIT_EVAL_ROOT") or Path(os.environ.get("SystemDrive", "C:") + "\\") / "omnikit-eval")
    path = root / "neutral"
    path.mkdir(parents=True, exist_ok=True)
    return path


def normalize_usage(agent, raw):
    if not raw:
        return None
    if agent == "claude":
        cached = raw.get("cache_read_input_tokens", 0)
        total = raw.get("input_tokens", 0) + raw.get("cache_creation_input_tokens", 0) + cached
        return {"input": total, "cached": cached, "output": raw.get("output_tokens", 0)}
    return {"input": raw.get("input_tokens", 0), "cached": raw.get("cached_input_tokens", 0), "output": raw.get("output_tokens", 0)}


def call(prompt, schema, agent="claude", model=None, timeout=600):
    """回傳 {"ok", "data", "usage", "error", "agent", "model"}。"""
    model = model or DEFAULT_MODEL.get(agent)
    result = {"ok": False, "data": None, "usage": None, "error": None, "agent": agent, "model": model}
    exe = shutil.which(agent)
    if not exe:
        result["error"] = f"找不到 {agent} 指令"
        return result
    try:
        if agent == "claude":
            cmd = [exe, "-p", "--output-format", "json", "--json-schema", json.dumps(schema, ensure_ascii=False),
                   "--tools", "", "--setting-sources", "", "--no-session-persistence"]
            if model:
                cmd += ["--model", model]
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=timeout, cwd=neutral_dir())
            try:
                doc = json.loads(proc.stdout)
            except json.JSONDecodeError:
                result["error"] = (proc.stderr or proc.stdout)[-300:] or f"claude 結束碼 {proc.returncode}"
                return result
            result["usage"] = normalize_usage("claude", doc.get("usage"))
            if doc.get("is_error") or doc.get("structured_output") is None:
                result["error"] = str(doc.get("result") or doc.get("terminal_reason") or "沒有結構化輸出")[:300]
                return result
            result.update(ok=True, data=doc["structured_output"])
            return result

        with tempfile.TemporaryDirectory(prefix="okcheap-") as tmp:
            schema_path = Path(tmp) / "schema.json"
            schema_path.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
            cmd = [exe, "exec", "--json", "--output-schema", str(schema_path), "--sandbox", "read-only",
                   "--ephemeral", "--skip-git-repo-check"]
            if model:
                cmd += ["-m", model]
            proc = subprocess.run(cmd + ["-"], input=prompt, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=timeout, cwd=neutral_dir(), shell=False)
        message, usage, error = None, None, None
        for line in proc.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = event.get("item") or {}
            if event.get("type") == "item.completed" and item.get("type") == "agent_message":
                message = item.get("text")
            elif event.get("type") == "turn.completed":
                usage = event.get("usage")
            elif event.get("type") in ("turn.failed", "error"):
                error = (event.get("error") or {}).get("message") or event.get("message")
        result["usage"] = normalize_usage("codex", usage)
        if message is None:
            result["error"] = (error or proc.stderr[-300:] or "沒有回覆")[:300]
            return result
        result.update(ok=True, data=json.loads(message))
        return result
    except subprocess.TimeoutExpired:
        result["error"] = f"超過 {timeout} 秒"
    except json.JSONDecodeError:
        result["error"] = "回覆不是 JSON"
    return result


class Fake:
    """自我測試用：依 prompt 裡的關鍵字回傳預先準備的結果，不呼叫模型。"""

    def __init__(self, answers):
        self.answers, self.prompts = answers, []

    def __call__(self, prompt, schema, agent="claude", model=None, timeout=600):
        self.prompts.append(prompt)
        for key, data in self.answers.items():
            if key in prompt:
                return {"ok": True, "data": data, "usage": {"input": 1000, "cached": 800, "output": 100},
                        "error": None, "agent": agent, "model": model or "fake"}
        return {"ok": False, "data": None, "usage": None, "error": "fake：沒有對應的答案", "agent": agent, "model": "fake"}
