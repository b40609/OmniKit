# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""單筆非互動工具評估 CLI（對接 OmniKeep 手機端工具評估閉環 軌 A）。

從 stdin 讀取單一 UTF-8 JSON，執行純唯讀 Layer 0（GitHub 現況、名冊查重、拒絕比對、安全掃描）
與 Layer 1（對照槽位現任、回應使用者提問與社群反例），從 stdout 輸出單一 UTF-8 JSON 物件。
所有除錯／錯誤日誌僅輸出至 stderr；max_layer <= 1 時嚴格禁止任何寫入或 Layer 2 實測動作。

用法：
  python scripts/eval_single.py --health
  python scripts/eval_single.py --version
  python scripts/eval_single.py < request.json
  uv run scripts/eval_single.py --selftest
"""
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

import _cheap
import _github
import _omnikit
import layer0
import layer1

SCHEMA_VERSION = "1.0"
CLI_VERSION = "1.0.0"
CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"


def _log(msg):
    sys.stderr.write(f"[omnikit-eval-single] {msg}\n")
    sys.stderr.flush()


def _slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or "candidate-tool"


def _normalize_url(target_url, repo):
    if target_url and str(target_url).strip().lower().startswith("https://"):
        return str(target_url).strip()
    if repo:
        return f"https://github.com/{repo}"
    if target_url and str(target_url).strip().lower().startswith("http://"):
        return "https://" + str(target_url).strip()[7:]
    return ""


def _layer1_validator():
    schema = json.loads((CONTRACTS / "layer1.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _health_doc():
    roster_ok = True
    roster_error = ""
    try:
        _omnikit.roster()
    except SystemExit as e:
        roster_ok = False
        roster_error = str(e)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if roster_ok else "error",
        "tool": "omnikit-eval-single",
        "version": CLI_VERSION,
        "omnikit_root": str(_omnikit.ROOT),
        "roster_ok": roster_ok,
        "contracts": {
            "layer1": (CONTRACTS / "layer1.schema.json").is_file(),
            "layer2_request": (CONTRACTS / "layer2-request.schema.json").is_file(),
        },
        "error": roster_error,
    }


def _error_response(message, security_badge="executable_needs_review", l0=None, l1=None):
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "error",
        "security_badge": security_badge,
        "layer0": l0,
        "layer1": l1,
        "slot_comparison": {"matched_slots": [], "incumbent_tools": [], "delta_summary": ""},
        "suggested_action": "reject",
        "error": str(message),
    }


def _heuristic_layer1(
    tool,
    l0,
    readme,
    roster,
    today,
    user_note="",
    source_summary="",
    community_counterpoints=None,
    fallback_reason="",
):
    """離線或便宜模型無法回應時的純唯讀啟發式 Layer 1 產出，完整對齊 layer1.schema.json。"""
    corpus = " ".join(
        filter(
            None,
            [
                tool.get("id", ""),
                tool.get("name", ""),
                (l0.get("github") or {}).get("description", ""),
                source_summary or "",
                user_note or "",
                (readme or "")[:6000],
            ],
        )
    )
    corpus_words = layer0.words(corpus)

    # 依非凍結槽位名稱與情境文字進行關鍵詞匹配
    scored_slots = []
    for slot in roster["slots"]:
        if slot.get("focus") == "frozen":
            continue
        slot_text = " ".join(
            [slot["id"], slot.get("name", "")] + [sc.get("text", "") for sc in (slot.get("scenarios") or [])]
        )
        overlap = len(corpus_words & layer0.words(slot_text))
        if overlap >= 2 or slot["id"] in (tool.get("slots") or []):
            scored_slots.append((overlap + (3 if slot["id"] in (tool.get("slots") or []) else 0), slot))
    scored_slots.sort(key=lambda item: (-item[0], item[1]["id"]))
    matched_slot_objs = [s for _, s in scored_slots[:2]]
    matched_slots = [s["id"] for s in matched_slot_objs]
    matched_scenarios = [sc["id"] for s in matched_slot_objs for sc in (s.get("scenarios") or [])][:4]

    natives_map = layer1.builtins(roster)
    native_by = [sid for sid in matched_slots if sid in natives_map]
    native_level = "partial" if native_by else "none"
    native_note = "；".join(f"{sid}：{natives_map[sid][:120]}" for sid in native_by) if native_by else "名冊未記錄對應內建功能已涵蓋"

    tools_values = list(roster["tools"].values())
    incumbent_names = [
        t["name"]
        for sid in matched_slots
        for t in tools_values
        if sid in t.get("slots", []) and t.get("status") in ("default", "trial")
    ]
    incumbent_names = list(dict.fromkeys(incumbent_names))

    desc = (l0.get("github") or {}).get("description") or (source_summary or "").strip() or tool["name"]
    summary_parts = [f"{tool['name']}：{desc[:140]}"]
    if (user_note or "").strip():
        summary_parts.append(f"針對提問「{user_note.strip()[:100]}」，需以實測檢驗 README 宣稱與實務表現。")
    summary = " ".join(summary_parts).strip()

    diff_parts = []
    if incumbent_names:
        diff_parts.append(f"對應槽位（{'、'.join(matched_slots)}）現任工具為{'、'.join(incumbent_names)}，此工具主張提供替代或補充能力，但尚未經第 2 層實測。")
    elif matched_slots:
        diff_parts.append(f"對應槽位（{'、'.join(matched_slots)}）目前無第三方現任，主要與內建功能對照。")
    else:
        diff_parts.append("尚未精確對應到 OmniKit 既有活躍槽位，建議先作情境備案或進一步確認需求範圍。")
    if (user_note or "").strip():
        diff_parts.append(f"回應使用者提問「{user_note.strip()[:120]}」：目前僅依據靜態 README 與來源摘要，尚未有獨立實測證據。")
    if community_counterpoints:
        pts = [
            (cp.strip() if isinstance(cp, str) else str(cp.get("point") or "").strip())
            for cp in community_counterpoints
        ]
        pts = [p for p in pts if p]
        if pts:
            diff_parts.append(f"社群反例指出限制：{'；'.join(pts[:3])}，不可只看原作者 README 宣傳。")

    claims = []
    badge = l0.get("security_badge") or "executable_needs_review"
    if badge == "risk_flagged":
        claims.append({
            "claim": "靜態安全掃描檢出高風險規則（risk_flagged）",
            "kind": "security",
            "how_to_verify": "人工逐檔審查高風險規則命中的程式碼片段與權限行為",
        })
    elif badge == "executable_needs_review":
        claims.append({
            "claim": "包含可執行碼／設定或缺少靜態 SKILL.md，尚未通過靜態安全審查",
            "kind": "security",
            "how_to_verify": "在隔離沙盒檢視安裝腳本、依賴與 MCP／CLI 執行指令",
        })
    if l0.get("repo"):
        claims.append({
            "claim": f"來源 repo 為 {l0['repo']}（星數 {(l0.get('github') or {}).get('stars', '未知')}）",
            "kind": "compat",
            "how_to_verify": "檢查實際環境相容性（含 Windows 與目標 agent 版本）",
        })

    if l0.get("verdict") == "fail" or badge == "risk_flagged":
        rec = "reject"
    elif matched_slots and any(s.get("focus") == "active" for s in matched_slot_objs) and native_level != "covered":
        rec = "deep_eval"
    else:
        rec = "keep_pending"

    needs_parts = []
    if fallback_reason:
        needs_parts.append(f"便宜模型未回應（{fallback_reason}），以下為規則初判待覆核")
    if not matched_slots:
        needs_parts.append("未能明確對應現有活躍槽位，請確認是否需要收為按需備案或拒絕")
    needs_user = "；".join(needs_parts)

    raw_data = {
        "slots": matched_slots,
        "scenarios": matched_scenarios,
        "summary": summary,
        "differences": " ".join(diff_parts).strip(),
        "claims": claims,
        "native_coverage": {"level": native_level, "by": native_by, "note": native_note},
        "cluster": _slugify(matched_slots[0] if matched_slots else tool["id"]),
        "recommendation": rec,
        "needs_user": needs_user,
    }
    raw_data = layer1.ensure_feedback_coverage(
        raw_data,
        user_note=user_note,
        community_counterpoints=community_counterpoints,
    )
    cleaned, dropped = layer1.clean(raw_data, roster)
    sim_rej = [
        {k: r[k] for k in ("id", "reason", "decided_at") if k in r}
        for r in ((l0.get("roster") or {}).get("similar_rejected") or [])
        if r.get("reason")
    ]
    doc = {
        "layer": 1,
        "tool_id": tool["id"],
        "name": tool["name"],
        "url": tool["url"],
        **cleaned,
        "similar_rejected": sim_rej,
        "meta": {
            "date": today.isoformat(),
            "agent": "claude",
            "model": None,
            "usage": None,
            "readme_sha": hashlib.sha256(readme.encode("utf-8")).hexdigest()[:12] if readme else None,
            "readme_chars": len(readme or ""),
            **({"dropped": dropped} if dropped else {}),
        },
    }
    return doc


def _build_slot_comparison(l1, roster):
    if not l1:
        return {
            "matched_slots": [],
            "incumbent_tools": [],
            "delta_summary": "未執行 Layer 1 槽位與現任比較。",
        }
    matched_slots = list(l1.get("slots") or [])
    tools_values = list(roster["tools"].values())
    slot_map = {s["id"]: s for s in roster["slots"]}

    incumbent_ids = []
    incumbent_labels = []
    for sid in matched_slots:
        slot_tools = [
            t for t in tools_values
            if sid in t.get("slots", []) and t.get("status") in ("default", "trial")
        ]
        if slot_tools:
            for t in slot_tools:
                if t["id"] not in incumbent_ids:
                    incumbent_ids.append(t["id"])
                    incumbent_labels.append(f"{t['name']}（{t['id']}）")
        else:
            slot = slot_map.get(sid) or {}
            has_native = any(
                (a or {}).get("verdict") == "native" for a in (slot.get("answers") or {}).values()
            )
            if has_native:
                native_tag = f"native:{sid}"
                if native_tag not in incumbent_ids:
                    incumbent_ids.append(native_tag)
                    incumbent_labels.append(f"內建功能（{sid}）")

    parts = []
    if matched_slots:
        parts.append(f"命中槽位：{'、'.join(matched_slots)}")
    else:
        parts.append("命中槽位：未分配（無對應現有槽位）")
    if incumbent_labels:
        parts.append(f"現任對照：{'、'.join(incumbent_labels)}")
    if l1.get("differences"):
        parts.append(l1["differences"])
    nc = l1.get("native_coverage") or {}
    if nc.get("level") and nc.get("level") != "none" and nc.get("note"):
        parts.append(f"內建涵蓋（{nc['level']}）：{nc['note']}")

    return {
        "matched_slots": matched_slots,
        "incumbent_tools": incumbent_ids,
        "delta_summary": "；".join(parts),
    }


def _suggest_action(l0, l1, security_badge):
    if (l0 or {}).get("verdict") == "fail" or security_badge == "risk_flagged":
        return "reject"
    if not l1:
        return "on_demand"
    rec = l1.get("recommendation")
    if rec == "reject":
        return "reject"
    nc_level = (l1.get("native_coverage") or {}).get("level")
    if nc_level == "covered" and rec != "deep_eval":
        return "reject"
    if rec == "deep_eval":
        return "approve_l2"
    return "on_demand"


def _ensure_layer1_fields(doc, validator):
    """補齊需求要求的 layer1 鍵並以 contracts/layer1.schema.json 驗證。"""
    normalized = {
        "layer": 1,
        "tool_id": doc["tool_id"],
        "name": doc["name"],
        "url": doc["url"],
        "slots": list(doc.get("slots") or []),
        "scenarios": list(doc.get("scenarios") or []),
        "summary": str(doc.get("summary") or ""),
        "differences": str(doc.get("differences") or ""),
        "claims": list(doc.get("claims") or []),
        "native_coverage": doc.get("native_coverage") or {"level": "none", "by": [], "note": ""},
        "recommendation": doc.get("recommendation") or "keep_pending",
        "needs_user": str(doc.get("needs_user") or ""),
    }
    for opt in ("cluster", "similar_rejected", "meta"):
        if opt in doc and doc[opt] is not None:
            normalized[opt] = doc[opt]
    validator.validate(normalized)
    return normalized


def evaluate_single(
    payload,
    *,
    roster=None,
    github_client=None,
    scan_fn=None,
    scanner_fn=None,
    cheap_fn=None,
    do_scan=True,
    no_llm=False,
    agent="claude",
    model=None,
    today=None,
    now=None,
    history_path=None,
):
    """執行單筆純唯讀工具評估（Layer 0 + Layer 1），絕不修改 OmniKit repo 內任何檔案。"""
    if not isinstance(payload, dict):
        return _error_response("stdin JSON 必須是單一 JSON 物件")

    max_layer_raw = payload.get("max_layer", 1)
    try:
        max_layer = int(max_layer_raw)
    except (TypeError, ValueError):
        return _error_response(f"max_layer 必須為整數，收到：{max_layer_raw!r}")
    if max_layer < 0:
        return _error_response(f"max_layer 不可為負數：{max_layer}")

    target_repo = str(payload.get("target_repo") or "").strip()
    target_url = str(payload.get("target_url") or "").strip()
    user_note = str(payload.get("user_note") or "").strip()
    source_summary = str(payload.get("source_summary") or "").strip()
    counterpoints = payload.get("community_counterpoints") or []
    if not isinstance(counterpoints, list):
        return _error_response("community_counterpoints 必須是陣列")

    parsed_repo = layer0.parse_repo(target_repo) or layer0.parse_repo(target_url)
    url = _normalize_url(target_url, parsed_repo)
    if not parsed_repo and not url:
        return _error_response("缺少有效的 target_repo 或 https:// target_url")

    today = today or date.today()
    now = now or datetime.now(timezone.utc)
    if roster is None:
        roster = _omnikit.roster()
    client = github_client or _github.Client()

    # ---------- Layer 0（純唯讀） ----------
    if parsed_repo:
        try:
            l0 = layer0.evaluate_target(
                parsed_repo,
                roster,
                do_scan=do_scan,
                client=client,
                scanner_fn=scanner_fn,
                scan_fn=scan_fn,
                now=now,
                history_path=history_path,
            )
            url = _normalize_url(target_url, l0["repo"]) or l0["url"]
        except (ValueError, LookupError, _github.GitHubError) as e:
            return _error_response(f"Layer 0 查詢失敗：{e}")
    else:
        sim_rej = layer0.similar_rejected("", source_summary or url, roster, history_path=history_path)
        l0 = {
            "layer": 0,
            "input": target_url,
            "repo": None,
            "url": url,
            "checked_at": now.strftime("%Y-%m-%d"),
            "omnikit_root": str(_omnikit.ROOT),
            "github": None,
            "roster": {"matches": [], "similar_rejected": sim_rej},
            "thresholds": [{"rule": "non_github", "level": "warn", "detail": "非 GitHub repo，無法執行自動安全掃描"}],
            "scan": {
                "ran": False,
                "error": "非 GitHub repo，略過 git 掃描",
                "skills": [],
                "duplicates_skipped": 0,
                "findings": [],
                "skill_count": 0,
                "has_executable_code": False,
                "executable_indicators_total": 0,
                "executable_indicators": [],
                "security_badge": "executable_needs_review",
                "security_reasons": ["非 GitHub repo，無法確認是否僅含靜態 SKILL.md，需人工檢視"],
            },
            "security_badge": "executable_needs_review",
            "verdict": "warn",
            "next": "進第 1 層：依據來源摘要與社群反例評析（非 GitHub repo，需人工審查）",
        }

    security_badge = l0.get("security_badge") or layer0.classify_security(l0.get("scan"))[0]

    # ---------- Layer 1（純唯讀；max_layer == 0 時跳過） ----------
    l1 = None
    if max_layer >= 1:
        matches = (l0.get("roster") or {}).get("matches") or []
        existing = roster["tools"].get(matches[0]["id"]) if matches else None
        if existing:
            tool = {**existing, "url": existing.get("url") or url}
        else:
            raw_name = l0["repo"].split("/")[1] if l0.get("repo") else (url.rstrip("/").split("/")[-1] or "candidate")
            tool = {
                "id": _slugify(raw_name),
                "name": l0["repo"] if l0.get("repo") else raw_name,
                "slots": [],
                "status": "pending",
                "url": url,
                "notes": source_summary[:500] if source_summary else "",
            }

        readme = None
        if l0.get("repo"):
            try:
                readme = client.rest(f"repos/{l0['repo']}/readme", raw=True)
            except _github.GitHubError as e:
                _log(f"讀取 README 失敗，將以來源摘要與社群反例繼續：{e}")
                readme = None

        entry = {
            "repo": l0.get("repo"),
            "github": {
                "stars": (l0.get("github") or {}).get("stars"),
                "created": (l0.get("github") or {}).get("created_at"),
                "license": (l0.get("github") or {}).get("license"),
                "description": (l0.get("github") or {}).get("description", ""),
            },
            "flags": [{"flag": c["rule"], "detail": c["detail"]} for c in (l0.get("thresholds") or [])],
            "compat": None,
        }

        use_no_llm = no_llm or os.environ.get("OMNIKIT_EVAL_NO_LLM") == "1"
        cheap = cheap_fn or _cheap.call
        l1_validator = _layer1_validator()
        doc = None
        fallback_reason = ""

        if not use_no_llm:
            doc, answer = layer1.evaluate(
                tool,
                entry,
                roster,
                client,
                cheap,
                agent,
                model,
                today,
                set(),
                user_note=user_note,
                source_summary=source_summary,
                community_counterpoints=counterpoints,
                readme=readme,
                history_path=history_path,
            )
            if doc is None:
                fallback_reason = str((answer or {}).get("error") or "模型未回傳結果")
                _log(f"Layer 1 模型呼叫未成功，改用規則初判：{fallback_reason}")

        if doc is None:
            doc = _heuristic_layer1(
                tool,
                l0,
                readme,
                roster,
                today,
                user_note=user_note,
                source_summary=source_summary,
                community_counterpoints=counterpoints,
                fallback_reason=fallback_reason,
            )

        try:
            l1 = _ensure_layer1_fields(doc, l1_validator)
        except Exception as e:
            _log(f"Layer 1 輸出契約驗證失敗，改用規則初判：{e}")
            doc = _heuristic_layer1(
                tool,
                l0,
                readme,
                roster,
                today,
                user_note=user_note,
                source_summary=source_summary,
                community_counterpoints=counterpoints,
                fallback_reason=f"契約驗證失敗：{e}",
            )
            l1 = _ensure_layer1_fields(doc, l1_validator)

    slot_comparison = _build_slot_comparison(l1, roster)
    suggested_action = _suggest_action(l0, l1, security_badge)

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok",
        "security_badge": security_badge,
        "layer0": l0,
        "layer1": l1,
        "slot_comparison": slot_comparison,
        "suggested_action": suggested_action,
        "error": "",
    }


def selftest():
    checks = []

    def check(name, ok):
        checks.append((name, bool(ok)))

    roster = {
        "slots": [
            {
                "id": "browser",
                "name": "瀏覽器",
                "focus": "active",
                "scenarios": [{"id": "U1", "text": "操作網頁並取得快照"}],
                "answers": {"claude": {"verdict": "unknown", "reason": "內建工具"}},
            }
        ],
        "tools": {
            "chrome-devtools-mcp": {
                "id": "chrome-devtools-mcp",
                "name": "Chrome DevTools MCP",
                "slots": ["browser"],
                "status": "trial",
                "reason": "現任試用",
                "decided_at": "2026-11-10",
                "trial_until": "2026-11-24",
            },
            "old-browser": {
                "id": "old-browser",
                "name": "Old Browser CLI",
                "slots": ["browser"],
                "status": "rejected",
                "url": "https://github.com/acme/old-browser",
                "reason": "Windows 閃退",
                "decided_at": "2026-11-01",
                "notes": "browser cli snapshot tool",
            },
        },
    }
    fake_gh = _github.Fake(
        rest={
            "repos/acme/fast-anything": {
                "full_name": "acme/fast-anything",
                "description": "Fast browser snapshot CLI",
                "stargazers_count": 320,
                "forks_count": 15,
                "license": {"spdx_id": "MIT"},
                "archived": False,
                "created_at": "2026-08-01T00:00:00Z",
                "pushed_at": "2026-11-20T00:00:00Z",
                "default_branch": "main",
            },
            "repos/acme/fast-anything/releases/latest": None,
            "repos/acme/fast-anything/readme": "# fast-anything\nFast browser CLI for snapshots.",
        }
    )

    with tempfile.TemporaryDirectory(prefix="okeval-single-") as tmp_dir:
        repo_dir = Path(tmp_dir)
        (repo_dir / "SKILL.md").write_text("# Skill\nStatic instructions only.\n", encoding="utf-8")
        (repo_dir / "package.json").write_text('{"name": "fast-anything"}', encoding="utf-8")

        fake_cheap = _cheap.Fake({
            "fast-anything": {
                "slots": ["browser"],
                "scenarios": ["U1"],
                "summary": "快速瀏覽器快照 CLI，回應是否支援 Windows：README 聲稱支援但社群回報路徑問題。",
                "differences": "與 Chrome DevTools MCP 相比不需 MCP server，但社群回報 Windows 長路徑會報錯。",
                "claims": [
                    {"claim": "支援 headless 快照", "kind": "capability", "how_to_verify": "在隔離目錄執行 snapshot 指令"}
                ],
                "native_coverage": {"level": "none", "by": [], "note": ""},
                "cluster": "browser-cli",
                "recommendation": "deep_eval",
                "needs_user": "",
            }
        })

        req = {
            "schema_version": "1.0",
            "request_id": "req-1",
            "source_item_id": "item-1",
            "eval_track": "tool",
            "target_url": "https://github.com/acme/fast-anything",
            "target_repo": "acme/fast-anything",
            "user_note": "Windows 能不能正常跑？",
            "source_summary": "X 貼文推薦的超快瀏覽器 CLI",
            "community_counterpoints": [
                {"point": "Windows 含空白路徑時會失敗", "category": "compat", "source": "GitHub Issues"}
            ],
            "max_layer": 1,
        }
        res = evaluate_single(
            req,
            roster=roster,
            github_client=fake_gh,
            scan_fn=lambda _repo: layer0.scan_local(
                repo_dir, sha="abc123", scanner_fn=lambda _p: {"max_severity": "SAFE", "findings": []}
            ),
            cheap_fn=fake_cheap,
            today=date(2026, 11, 24),
            now=datetime(2026, 11, 24, tzinfo=timezone.utc),
            history_path=False,
        )

    check("回傳 status=ok 與 schema_version=1.0", res["status"] == "ok" and res["schema_version"] == "1.0" and res["error"] == "")
    check("含 package.json 判為 executable_needs_review 且 layer0 verdict 非 pass",
          res["security_badge"] == "executable_needs_review" and res["layer0"]["verdict"] == "warn")
    check("prompt 納入 user_note 與 community_counterpoints",
          fake_cheap.prompts and "Windows 能不能正常跑" in fake_cheap.prompts[0] and "Windows 含空白路徑時會失敗" in fake_cheap.prompts[0])
    check("layer1 符合 schema 且社群反例自動進入 claims 待驗證",
          any("空白路徑" in c["claim"] for c in res["layer1"]["claims"]) and "needs_user" in res["layer1"])
    check("slot_comparison 命中 browser 與現任 chrome-devtools-mcp",
          res["slot_comparison"]["matched_slots"] == ["browser"]
          and res["slot_comparison"]["incumbent_tools"] == ["chrome-devtools-mcp"])
    check("suggested_action 為 approve_l2", res["suggested_action"] == "approve_l2")

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'✓' if ok else '✗'} {name}")
    print(f"eval_single 自我測試：{len(checks) - len(failed)}/{len(checks)} 通過")
    return 1 if failed else 0


def main(argv=None):
    _omnikit.utf8_stdio()
    parser = argparse.ArgumentParser(description="OmniKit 單筆非互動工具評估 CLI")
    parser.add_argument("--health", action="store_true", help="印出健康狀態 JSON 並以 0 結束")
    parser.add_argument("--version", action="store_true", help="印出版本 JSON 並以 0 結束")
    parser.add_argument("--no-scan", action="store_true", help="略過 git clone 安全掃描")
    parser.add_argument("--no-llm", action="store_true", help="不呼叫便宜模型，改用規則初判")
    parser.add_argument("--agent", choices=["claude", "codex"], default=os.environ.get("OMNIKIT_EVAL_AGENT", "claude"))
    parser.add_argument("--model", default=os.environ.get("OMNIKIT_EVAL_MODEL"))
    parser.add_argument("--selftest", action="store_true", help="執行離線自我測試")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.version:
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "status": "ok",
            "tool": "omnikit-eval-single",
            "version": CLI_VERSION,
        }, ensure_ascii=False))
        return 0
    if args.health:
        print(json.dumps(_health_doc(), ensure_ascii=False))
        return 0

    raw = sys.stdin.read()
    if not raw.strip():
        doc = _error_response("stdin 為空，未收到評估請求 JSON")
        _log(doc["error"])
        print(json.dumps(doc, ensure_ascii=False))
        return 0

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        doc = _error_response(f"stdin JSON 解析失敗：{e}")
        _log(doc["error"])
        print(json.dumps(doc, ensure_ascii=False))
        return 0

    try:
        result = evaluate_single(
            payload,
            do_scan=not args.no_scan,
            no_llm=args.no_llm,
            agent=args.agent,
            model=args.model,
        )
    except Exception as e:
        _log(f"未預期錯誤：{e}")
        result = _error_response(f"執行評估時發生錯誤：{e}")

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
