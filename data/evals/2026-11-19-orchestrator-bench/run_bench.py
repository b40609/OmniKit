"""執行 Orchestrator (Neon) vs Gemini 4 Neon (High) 同題對照實測。"""
import json
import subprocess
import time
from pathlib import Path

from verify_bench import BASE, setup_sandboxes, verify_dir

PROMPT = (
    "請先讀目前工作目錄的 SPEC.md 與 fixtures/ 裡的樣本檔，"
    "依 SPEC.md 完整實作 model_router/（catalog.py、resolver.py、cli.py、__init__.py）"
    "與 tests/test_model_router.py，並實際執行 `python -m unittest discover -s tests -v` "
    "確認全部通過。禁止讀寫目前工作目錄以外的任何檔案。完成後只輸出 5 行內的摘要。"
)


def run_one(name: str, model: str, workdir: Path) -> dict:
    log_path = BASE / f"log_{name}.txt"
    out_path = BASE / f"result_{name}.json"
    cmd = [
        "agy",
        "-p",
        PROMPT,
        "--model",
        model,
        "--output-format",
        "json",
        "--disable-slash-commands",
        "--dangerously-skip-permissions",
        "--print-timeout",
        "600s",
        "--log-file",
        str(log_path),
    ]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, encoding="utf-8", errors="replace")
    wall = round(time.perf_counter() - t0, 2)

    parsed = None
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                parsed = json.loads(line)
                break
            except json.JSONDecodeError:
                pass
    if parsed is None:
        try:
            parsed = json.loads(proc.stdout)
        except Exception:
            parsed = {"raw_stdout": proc.stdout[-1000:], "raw_stderr": proc.stderr[-1000:]}

    out_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")

    # 統計產出程式碼行數與檔案數
    py_files = sorted(p for p in workdir.rglob("*.py"))
    loc = sum(len(p.read_text(encoding="utf-8", errors="replace").splitlines()) for p in py_files)
    verify = verify_dir(workdir)

    return {
        "name": name,
        "model": model,
        "returncode": proc.returncode,
        "wall_seconds": wall,
        "duration_seconds": parsed.get("duration_seconds") if isinstance(parsed, dict) else None,
        "num_turns": parsed.get("num_turns") if isinstance(parsed, dict) else None,
        "status": parsed.get("status") if isinstance(parsed, dict) else None,
        "finished_reason": parsed.get("finished_reason") if isinstance(parsed, dict) else None,
        "usage": parsed.get("usage") if isinstance(parsed, dict) else None,
        "error": parsed.get("error") if isinstance(parsed, dict) else None,
        "py_files": [str(p.relative_to(workdir)) for p in py_files],
        "total_loc": loc,
        "verify": verify,
        "log_size_bytes": log_path.stat().st_size if log_path.exists() else 0,
    }


def main():
    setup_sandboxes()
    results = []
    for name, model, folder in [
        ("orchestrator_neon", "gemini-pro-orchestrator-neon", BASE / "run_orchestrator"),
        ("neon_high", "gemini-4-neon-high", BASE / "run_neon_high"),
    ]:
        print(f"=== Running {name} ({model}) ===", flush=True)
        res = run_one(name, model, folder)
        results.append(res)
        print(
            f"Done {name}: rc={res['returncode']} wall={res['wall_seconds']}s "
            f"turns={res['num_turns']} verify={res['verify']['passed']}/{res['verify']['total']} "
            f"usage={res['usage']}",
            flush=True,
        )

    summary_path = BASE / "summary.json"
    summary_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {summary_path}")


if __name__ == "__main__":
    main()
