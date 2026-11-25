"""評估 skill 各腳本共用：找到 OmniKit repo、讀名冊、輸出 JSON。"""
import json
import os
import sys
from pathlib import Path


def repo_root():
    """找 OmniKit repo：優先看 OMNIKIT_HOME；次看連結解析（若落在 ~/.omnikit/current 則優先轉回 config.json 的開發 repo）；
    最後看 ~/.omnikit/config.json。"""
    env = os.environ.get("OMNIKIT_HOME")
    if env and (Path(env) / "data" / "omnikit.yaml").exists():
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "data" / "omnikit.yaml").exists():
            if parent.name == "current":
                if (parent.parent / "config.json").is_file():
                    try:
                        cfg_repo = Path(json.loads((parent.parent / "config.json").read_text(encoding="utf-8-sig"))["repo"])
                        if (cfg_repo / "data" / "omnikit.yaml").exists():
                            return cfg_repo
                    except (OSError, ValueError, KeyError, TypeError):
                        pass
                sys.stderr.write(
                    f"警告：目前落在乾淨參照副本 {parent}（config.json 無有效 repo 欄位），請在開發倉庫執行 uv run engine/scripts/sync.py sync\n"
                )
            return parent
    state = Path(os.environ.get("OMNIKIT_STATE_DIR") or (Path.home() / ".omnikit"))
    for candidate_fn in (
        lambda: Path(json.loads((state / "config.json").read_text(encoding="utf-8-sig"))["repo"]),
        lambda: state / "current",
    ):
        try:
            cand = candidate_fn()
            if (cand / "data" / "omnikit.yaml").exists():
                return cand
        except (OSError, ValueError, KeyError, TypeError):
            pass
    sys.exit("找不到 OmniKit repo：請把環境變數 OMNIKIT_HOME 設成 repo 根目錄")


ROOT = repo_root()
sys.path.insert(0, str(ROOT / "engine" / "scripts"))
import validate  # 共用名冊的讀取與驗證


def roster():
    errors, data = validate.check(ROOT / "data")
    if errors:
        sys.exit("名冊驗證失敗，先修正：\n" + "\n".join(f"- {e}" for e in errors))
    return data


def card_summary(tool):
    keys = ("id", "name", "status", "slots", "url", "reason", "trigger_when", "decided_at", "trial_until", "notes")
    return {k: tool[k] for k in keys if k in tool}


def emit(doc):
    utf8_stdout()
    print(json.dumps(doc, ensure_ascii=False, indent=2))


def utf8_stdout():
    # 自我測試會把 stdout 換成 StringIO，它沒有 reconfigure
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def utf8_stdio():
    """確保 Windows 環境下 stdin/stdout/stderr 皆為 UTF-8，不因 cp950/cp1252 亂碼。"""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass
