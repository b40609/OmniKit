"""建立 Orchestrator vs Neon High 對照實測的沙盒，並提供獨立客觀驗收測試。"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent

T3_CAPS_SAMPLE = {
    "providers": [
        {
            "providerInstanceId": "codex",
            "driverKind": "codex",
            "models": [],
            "canRunChildTask": False,
            "constraints": ["Provider instance is disabled."],
        },
        {
            "providerInstanceId": "grok",
            "driverKind": "grok",
            "models": [{"id": "grok-build", "label": "Grok Build"}],
            "canRunChildTask": False,
            "constraints": ["Provider instance is disabled."],
        },
        {
            "providerInstanceId": "claudeAgent",
            "driverKind": "claudeAgent",
            "models": [
                {
                    "id": "claude-opus-5-5",
                    "label": "Claude Opus 5.5",
                    "options": [
                        {"id": "effort", "values": ["low", "medium", "high", "xhigh", "max", "ultrathink"], "default": "medium"},
                        {"id": "ultracode", "values": [False, True]},
                    ],
                },
                {
                    "id": "claude-sonnet-5-5",
                    "label": "Claude Sonnet 5.5",
                    "options": [
                        {"id": "effort", "values": ["low", "medium", "high", "xhigh", "max", "ultrathink"], "default": "high"},
                    ],
                },
            ],
            "canRunChildTask": True,
            "constraints": [],
        },
        {
            "providerInstanceId": "antigravity",
            "driverKind": "antigravity",
            "models": [
                {
                    "id": "gemini-4-hydrogen",
                    "label": "Gemini 4 Hydrogen",
                    "options": [{"id": "thinking_level", "values": ["low", "medium", "high", "xhigh"], "default": "high"}],
                },
                {
                    "id": "gemini-4-argon",
                    "label": "Gemini 4 Argon",
                    "options": [{"id": "thinking_level", "values": ["low", "medium", "high"], "default": "high"}],
                },
                {
                    "id": "gemini-4-neon",
                    "label": "Gemini 4 Neon",
                    "options": [{"id": "thinking_level", "values": ["low", "medium", "high", "xhigh"], "default": "high"}],
                },
                {
                    "id": "claude-opus-5-5",
                    "label": "Claude Opus 5.5",
                    "options": [{"id": "thinking_level", "values": ["low", "medium", "high"], "default": "medium"}],
                },
            ],
            "canRunChildTask": True,
            "constraints": [],
        },
        {
            "providerInstanceId": "antigravity_ava",
            "driverKind": "antigravity",
            "models": [
                {
                    "id": "gemini-3.8-flash",
                    "label": "Gemini 3.8 Flash",
                    "options": [{"id": "thinking_level", "values": ["low", "medium", "high"], "default": "high"}],
                }
            ],
            "canRunChildTask": True,
            "constraints": [],
        },
    ]
}

AGY_MODELS_SAMPLE = """Fetching available models...
gemini-4-neon-high\tGemini 4 Neon (High)
gemini-4-neon-xhigh\tGemini 4 Neon (XHigh)
gemini-4-hydrogen-high\tGemini 4 Hydrogen (High)
gemini-pro-orchestrator-neon\tOrchestrator (Neon)
gemini-pro-orchestrator-g1-pro\tOrchestrator (Argon)
gemini-3.8-flash-high\tGemini 3.8 Flash (High)
claude-opus-5-5-medium\tClaude Opus 5.5 (Medium)
gpt-oss-120b-medium\tGPT-OSS 120B (Medium)
"""


def setup_sandboxes():
    for name in ("run_orchestrator", "run_neon_high"):
        d = BASE / name
        if d.exists():
            shutil.rmtree(d)
        (d / "fixtures").mkdir(parents=True, exist_ok=True)
        shutil.copy2(BASE / "SPEC.md", d / "SPEC.md")
        (d / "fixtures" / "t3_caps.json").write_text(
            json.dumps(T3_CAPS_SAMPLE, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (d / "fixtures" / "agy_models.txt").write_text(AGY_MODELS_SAMPLE, encoding="utf-8")
    print("Sandboxes ready.")


def verify_dir(target_dir: Path) -> dict:
    """在隔離環境跑 14 項獨立客觀驗收測試。"""
    results = []

    def check(name: str, fn):
        try:
            fn()
            results.append({"name": name, "ok": True})
        except Exception as e:
            results.append({"name": name, "ok": False, "error": f"{type(e).__name__}: {e}"})

    # 1. 自己寫的 unittest 是否全部通過
    def test_own_unittest():
        r = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=target_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert r.returncode == 0, f"own tests failed: {r.stderr[-300:]}"

    check("own_unittest_pass", test_own_unittest)

    # 動態匯入受測套件
    sys_path_orig = list(sys.path)
    for k in list(sys.modules):
        if k == "model_router" or k.startswith("model_router."):
            del sys.modules[k]
    sys.path.insert(0, str(target_dir))
    try:
        from model_router.catalog import parse_t3_capabilities, parse_agy_models, diff_catalogs
        from model_router.resolver import resolve_role

        items = parse_t3_capabilities(T3_CAPS_SAMPLE)

        def t_parse_t3_count_and_enabled():
            assert len(items) == 8, f"expected 8 models, got {len(items)}"
            grok = [x for x in items if x["provider_id"] == "grok"][0]
            assert grok["enabled"] is False
            assert grok["thinking_param"] is None and grok["thinking_values"] == []
            neon = [x for x in items if x["model_id"] == "gemini-4-neon"][0]
            assert neon["enabled"] is True and neon["thinking_param"] == "thinking_level"
            assert "xhigh" in neon["thinking_values"] and neon["default_thinking"] == "high"
            opus = [x for x in items if x["provider_id"] == "claudeAgent" and x["model_id"] == "claude-opus-5-5"][0]
            assert opus["thinking_param"] == "effort" and opus["default_thinking"] == "medium"

        check("parse_t3_capabilities", t_parse_t3_count_and_enabled)

        def t_parse_agy():
            agy = parse_agy_models(AGY_MODELS_SAMPLE)
            assert len(agy) == 8, f"expected 8 agy models, got {len(agy)}"
            orch = [x for x in agy if x["model_id"] == "gemini-pro-orchestrator-neon"][0]
            assert orch["base_model"] == "gemini-pro-orchestrator-neon" and orch["thinking_suffix"] is None
            neon = [x for x in agy if x["model_id"] == "gemini-4-neon-xhigh"][0]
            assert neon["base_model"] == "gemini-4-neon" and neon["thinking_suffix"] == "xhigh"
            gpt = [x for x in agy if x["model_id"] == "gpt-oss-120b-medium"][0]
            assert gpt["base_model"] == "gpt-oss-120b" and gpt["thinking_suffix"] == "medium"

        check("parse_agy_models", t_parse_agy)

        def t_diff():
            old = parse_t3_capabilities(T3_CAPS_SAMPLE)
            new_raw = json.loads(json.dumps(T3_CAPS_SAMPLE))
            # 移除 argon、新增 gemini-5-beta、改 flash thinking_values
            ag = [p for p in new_raw["providers"] if p["providerInstanceId"] == "antigravity"][0]
            ag["models"] = [m for m in ag["models"] if m["id"] != "gemini-4-argon"]
            ag["models"].append({"id": "gemini-5-beta", "label": "Gemini 5 Beta", "options": []})
            ava = [p for p in new_raw["providers"] if p["providerInstanceId"] == "antigravity_ava"][0]
            ava["models"][0]["options"][0]["values"] = ["low", "medium", "high", "xhigh"]
            d = diff_catalogs(old, parse_t3_capabilities(new_raw))
            assert len(d["added"]) == 1 and d["added"][0]["model_id"] == "gemini-5-beta"
            assert len(d["removed"]) == 1 and d["removed"][0]["model_id"] == "gemini-4-argon"
            assert len(d["changed"]) == 1 and "thinking_values" in d["changed"][0]["changes"]

        check("diff_catalogs", t_diff)

        policy = {
            "roles": {
                "gemini-strong": {
                    "forbid_thinking": ["low", "medium"],
                    "candidates": [
                        {
                            "provider_id": "antigravity",
                            "model_pattern": "gemini-4-*",
                            "exclude_patterns": ["*-argon*"],
                            "prefer_order": ["gemini-4-neon", "gemini-4-hydrogen"],
                            "thinking": "high",
                        }
                    ],
                },
                "gemini-xhigh-fallback": {
                    "forbid_thinking": ["low", "medium"],
                    "candidates": [
                        {"provider_id": "antigravity_ava", "model_pattern": "gemini-*", "thinking": "xhigh"},
                        {"provider_id": "antigravity", "model_pattern": "gemini-4-hydrogen", "thinking": "xhigh"},
                    ],
                },
                "disabled-only": {
                    "forbid_thinking": [],
                    "candidates": [{"provider_id": "grok", "model_pattern": "*", "thinking": "high"}],
                },
            }
        }

        def t_resolve_prefer_order():
            r = resolve_role("gemini-strong", policy, items)
            assert r["ok"] is True and r["model_id"] == "gemini-4-neon" and r["fallback_index"] == 0
            assert r["matched_by"] == "policy" and r["thinking_param"] == "thinking_level"

        check("resolve_prefer_order", t_resolve_prefer_order)

        def t_resolve_fallback():
            r = resolve_role("gemini-xhigh-fallback", policy, items)
            assert r["ok"] is True and r["model_id"] == "gemini-4-hydrogen" and r["fallback_index"] == 1

        check("resolve_fallback_on_unsupported_thinking", t_resolve_fallback)

        def t_resolve_disabled_skipped():
            r = resolve_role("disabled-only", policy, items)
            assert r["ok"] is False and r["reason"] == "no_candidate_available"

        check("resolve_skip_disabled_provider", t_resolve_disabled_skipped)

        def t_resolve_unknown_role():
            r = resolve_role("nonexistent", policy, items)
            assert r["ok"] is False and r["reason"] == "unknown_role"

        check("resolve_unknown_role", t_resolve_unknown_role)

        def t_override_valid():
            r = resolve_role(
                "gemini-strong",
                policy,
                items,
                overrides={"gemini-strong": {"provider_id": "antigravity", "model_id": "gemini-4-hydrogen", "thinking": "xhigh"}},
            )
            assert r["ok"] is True and r["model_id"] == "gemini-4-hydrogen" and r["thinking"] == "xhigh"
            assert r["matched_by"] == "override" and r["fallback_index"] == -1

        check("resolve_override_valid", t_override_valid)

        def t_override_forbidden_thinking():
            r = resolve_role(
                "gemini-strong",
                policy,
                items,
                overrides={"gemini-strong": {"provider_id": "antigravity", "model_id": "gemini-4-neon", "thinking": "low"}},
            )
            assert r["ok"] is False and r["reason"] == "forbidden_thinking"

        check("resolve_override_forbidden_thinking", t_override_forbidden_thinking)

        def t_override_unavailable():
            r = resolve_role(
                "gemini-strong",
                policy,
                items,
                overrides={"gemini-strong": {"provider_id": "grok", "model_id": "grok-build", "thinking": "high"}},
            )
            assert r["ok"] is False and r["reason"] == "override_unavailable"

        check("resolve_override_unavailable", t_override_unavailable)

        def t_override_unsupported_thinking():
            r = resolve_role(
                "gemini-strong",
                policy,
                items,
                overrides={"gemini-strong": {"provider_id": "antigravity_ava", "model_id": "gemini-3.8-flash", "thinking": "xhigh"}},
            )
            assert r["ok"] is False and r["reason"] == "unsupported_thinking"

        check("resolve_override_unsupported_thinking", t_override_unsupported_thinking)

        # CLI tests
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            pol_p = tdp / "policy.json"
            pol_p.write_text(json.dumps(policy), encoding="utf-8")
            t3_p = target_dir / "fixtures" / "t3_caps.json"
            agy_p = target_dir / "fixtures" / "agy_models.txt"

            def t_cli_catalog():
                r = subprocess.run(
                    [sys.executable, "-m", "model_router.cli", "catalog", "--t3", str(t3_p), "--agy", str(agy_p), "--json"],
                    cwd=target_dir, capture_output=True, text=True, timeout=15,
                )
                assert r.returncode == 0, r.stderr
                data = json.loads(r.stdout)
                assert isinstance(data, (list, dict))

            check("cli_catalog", t_cli_catalog)

            def t_cli_resolve_ok_and_fail():
                r1 = subprocess.run(
                    [sys.executable, "-m", "model_router.cli", "resolve", "--role", "gemini-strong", "--policy", str(pol_p), "--t3", str(t3_p), "--json"],
                    cwd=target_dir, capture_output=True, text=True, timeout=15,
                )
                assert r1.returncode == 0, r1.stderr
                assert json.loads(r1.stdout)["model_id"] == "gemini-4-neon"
                r2 = subprocess.run(
                    [sys.executable, "-m", "model_router.cli", "resolve", "--role", "gemini-strong", "--policy", str(pol_p), "--t3", str(t3_p), "--override", "antigravity:gemini-4-neon:low", "--json"],
                    cwd=target_dir, capture_output=True, text=True, timeout=15,
                )
                assert r2.returncode == 2, f"expected exit 2, got {r2.returncode}"
                assert json.loads(r2.stdout)["reason"] == "forbidden_thinking"

            check("cli_resolve_exit_codes", t_cli_resolve_ok_and_fail)
    finally:
        sys.path = sys_path_orig

    passed = sum(1 for x in results if x["ok"])
    return {"passed": passed, "total": len(results), "details": results}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        setup_sandboxes()
    elif len(sys.argv) > 2 and sys.argv[1] == "verify":
        out = verify_dir(Path(sys.argv[2]))
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print("Usage: verify_bench.py setup | verify <dir>")
