# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""拍板回寫 CLI（對接 OmniKeep 手機端工具評估閉環 軌 A）。

從 stdin 讀取單一 UTF-8 JSON，依 decision（approve_l2 / on_demand / reject）落地：
- approve_l2：建立／更新待實測工單，產出符合 contracts/layer2-request.schema.json 的請求檔並登記 layer2-todo.md。
- on_demand：依 Progressive Disclosure 原則寫入名冊並設 status: "on_demand" 與 trigger_when，不載入常駐規則／工作流（0 token 常駐）。
- reject：寫入名冊 status: "rejected" 與 data/funnel/rejected-history.jsonl，確保下次 layer0.py 遇見同 repo 或同類工具命中 similar_rejected。

所有日誌走 stderr，stdout 僅輸出單一 UTF-8 JSON 物件。

用法：
  python scripts/record_decision.py --health
  python scripts/record_decision.py --version
  python scripts/record_decision.py [--data <資料目錄>] < decision.json
  uv run scripts/record_decision.py --selftest
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

import _omnikit
import layer0
import validate

SCHEMA_VERSION = "1.0"
CLI_VERSION = "1.0.0"
VALID_DECISIONS = ("approve_l2", "on_demand", "reject")
CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"


def _log(msg):
    sys.stderr.write(f"[omnikit-record-decision] {msg}\n")
    sys.stderr.flush()


def _slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or "candidate-tool"


def _normalize_date(raw, fallback=None):
    text = str(raw or "").strip()
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    if m:
        return m.group(1)
    return (fallback or date.today()).isoformat()


def _normalize_url(target_url, repo):
    u = str(target_url or "").strip()
    if u.lower().startswith("https://"):
        return u
    if repo:
        return f"https://github.com/{repo}"
    if u.lower().startswith("http://"):
        return "https://" + u[7:]
    return ""


def _write_yaml(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=1000)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _write_json(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _layer2_request_validator():
    schema = json.loads((CONTRACTS / "layer2-request.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _resolve_tool_id(payload, repo, roster):
    """優先命中名冊同 repo 既有卡片 id，否則正規化 payload.tool_id 或 repo 名稱。"""
    if repo:
        matches = layer0.roster_matches(repo, roster)
        if matches:
            return matches[0]["id"]
    raw_id = str(payload.get("tool_id") or "").strip()
    if raw_id:
        return _slugify(raw_id)
    if repo and "/" in repo:
        return _slugify(repo.split("/")[1])
    url = str(payload.get("target_url") or "").strip().rstrip("/")
    if url:
        return _slugify(url.split("/")[-1])
    return ""


def _merge_sources(existing_sources, source_item_id):
    sources = list(existing_sources or [])
    tag = f"omnikeep:{source_item_id}" if source_item_id else "omnikeep"
    if tag not in sources:
        sources.append(tag)
    return sources


def _append_note(existing_notes, addition):
    base = str(existing_notes or "").strip()
    add = str(addition or "").strip()
    if not add:
        return base
    if add in base:
        return base
    return f"{base}\n{add}".strip() if base else add


def _valid_slots(raw_slots, roster):
    known = {s["id"] for s in roster["slots"]}
    out = []
    for s in raw_slots or []:
        if isinstance(s, str) and s in known and s not in out:
            out.append(s)
    return out


def _build_layer2_request(tool_id, payload, existing_card, roster, funnel_dir):
    req_in = payload.get("layer2_request") if isinstance(payload.get("layer2_request"), dict) else {}
    slot_map = {s["id"]: s for s in roster["slots"]}
    known_slots = set(slot_map)

    # 1. 槽位推導
    slot_id = req_in.get("slot")
    if not isinstance(slot_id, str) or not slot_id.strip():
        cand_slots = _valid_slots(payload.get("slots"), roster)
        if not cand_slots and existing_card:
            cand_slots = _valid_slots(existing_card.get("slots"), roster)
        if not cand_slots:
            l1_path = funnel_dir / "layer1" / f"{tool_id}.json"
            if l1_path.is_file():
                try:
                    l1_doc = json.loads(l1_path.read_text(encoding="utf-8"))
                    cand_slots = _valid_slots(l1_doc.get("slots"), roster)
                except (OSError, ValueError):
                    cand_slots = []
        if cand_slots:
            slot_id = cand_slots[0]
        else:
            active_slot = next((s["id"] for s in roster["slots"] if s.get("focus") == "active"), None)
            slot_id = active_slot or (roster["slots"][0]["id"] if roster["slots"] else "unassigned")
    slot_id = slot_id.strip()

    # 2. 情境推導（至少 1 筆）
    scenarios = [s for s in (req_in.get("scenarios") or []) if isinstance(s, str) and s.strip()]
    if not scenarios and slot_id in slot_map:
        scenarios = [sc["id"] for sc in (slot_map[slot_id].get("scenarios") or []) if sc.get("id")]
    if not scenarios:
        scenarios = ["TBD"]

    # 3. 候選名單（2 到 3 個：現任 + 挑戰者）
    raw_candidates = req_in.get("candidates")
    candidates = []
    if isinstance(raw_candidates, list):
        for c in raw_candidates:
            if isinstance(c, dict) and c.get("id") and c.get("role") in ("incumbent", "challenger"):
                candidates.append({"id": str(c["id"]), "role": c["role"]})
    if not (2 <= len(candidates) <= 3):
        incumbents = [
            t["id"] for t in roster["tools"].values()
            if slot_id in t.get("slots", []) and t.get("status") in ("trial", "default") and t["id"] != tool_id
        ]
        if not incumbents:
            incumbents = [f"native-{slot_id}"]
        candidates = [{"id": inc, "role": "incumbent"} for inc in incumbents[:2]]
        candidates.append({"id": tool_id, "role": "challenger"})
    candidates = candidates[:3]

    # 4. 決策規則、執行者、評審與寫入邊界
    note = str(payload.get("decision_note") or "").strip()
    default_rule = (
        f"於隔離沙盒驗證 {tool_id} 在槽位 {slot_id} 的實際表現與社群反例"
        + (f"（重點：{note}）" if note else "")
        + "；若淨勝現任基準且安全審查通過則進試用（Update），否則維持現任（Keep）或改列按需備案。"
    )
    decision_rule = str(req_in.get("decision_rule") or "").strip() or default_rule
    runner = str(req_in.get("runner") or "").strip() or "anthropic"
    judge = str(req_in.get("judge") or "").strip() or ("google" if runner != "google" else "anthropic")

    raw_limits = req_in.get("limits") if isinstance(req_in.get("limits"), dict) else {}
    limits = {
        "write_scope": str(raw_limits.get("write_scope") or "data/"),
        "allow_push": bool(raw_limits.get("allow_push", False)),
    }
    max_minutes = raw_limits.get("max_minutes", 30)
    if isinstance(max_minutes, int) and max_minutes >= 1:
        limits["max_minutes"] = max_minutes

    req_doc = {
        "slot": slot_id,
        "scenarios": scenarios,
        "candidates": candidates,
        "decision_rule": decision_rule,
        "runner": runner,
        "judge": judge,
        "limits": limits,
    }
    _layer2_request_validator().validate(req_doc)
    return req_doc, (slot_id if slot_id in known_slots else None)


def _upsert_layer2_todo(todo_path, tool_id, req_doc, req_rel_path, note=""):
    incumbents = [c["id"] for c in req_doc["candidates"] if c["role"] == "incumbent"]
    inc_text = "、".join(incumbents) if incumbents else "（無現任）"
    extra = f"；{note}" if note else ""
    new_line = f"- [ ] {req_doc['slot']}：{inc_text} 對 {tool_id}（客觀；OmniKeep 核准實測，請求檔 {req_rel_path}{extra}）"

    todo_path.parent.mkdir(parents=True, exist_ok=True)
    if todo_path.is_file():
        lines = todo_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = ["# 第 2 層待測清單（手寫）", ""]

    marker = f"layer2-requests/{tool_id}.json"
    replaced = False
    for idx, line in enumerate(lines):
        if line.startswith("- [ ] ") and (marker in line or re.search(rf"對\s+[^\n]*\b{re.escape(tool_id)}\b", line)):
            lines[idx] = new_line
            replaced = True
            break
    if not replaced:
        lines.append(new_line)

    tmp = todo_path.with_suffix(todo_path.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, todo_path)


def _upsert_rejected_history(history_path, entry):
    history_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    if history_path.is_file():
        for line in history_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    updated = False
    for idx, r in enumerate(rows):
        same_id = r.get("tool_id") == entry["tool_id"]
        same_repo = entry.get("repo") and r.get("repo") and r["repo"].lower() == entry["repo"].lower()
        if same_id or same_repo:
            rows[idx] = entry
            updated = True
            break
    if not updated:
        rows.append(entry)

    tmp = history_path.with_suffix(history_path.suffix + ".tmp")
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, history_path)


def _error_response(message, decision="", tool_id=""):
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "error",
        "decision": decision,
        "tool_id": tool_id,
        "written_files": [],
        "error": str(message),
    }


def _health_doc(data_dir=None):
    data_path = Path(data_dir) if data_dir else (_omnikit.ROOT / "data")
    errors, _ = validate.check(data_path)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if not errors else "error",
        "tool": "omnikit-record-decision",
        "version": CLI_VERSION,
        "omnikit_root": str(_omnikit.ROOT),
        "data_dir": str(data_path),
        "roster_ok": not errors,
        "contracts": {
            "layer2_request": (CONTRACTS / "layer2-request.schema.json").is_file(),
        },
        "error": "；".join(errors[:3]) if errors else "",
    }


def record_decision(payload, *, data_dir=None, funnel_dir=None, state_dir=None, today=None):
    """將手機端拍板決定落地到 OmniKit 資料層，並執行 validate.check() 驗證。"""
    if not isinstance(payload, dict):
        return _error_response("stdin JSON 必須是單一 JSON 物件")

    decision = str(payload.get("decision") or "").strip()
    if decision not in VALID_DECISIONS:
        return _error_response(
            f"不支援的 decision：{decision!r}，僅接受 {', '.join(VALID_DECISIONS)}",
            decision=decision,
        )

    data_path = Path(data_dir) if data_dir else (_omnikit.ROOT / "data")
    funnel_path = Path(funnel_dir) if funnel_dir else (data_path / "funnel")
    today = today or date.today()

    errors, roster = validate.check(data_path, state=state_dir)
    if errors:
        return _error_response(f"寫入前名冊驗證失敗：{'；'.join(errors[:3])}", decision=decision)

    target_repo = str(payload.get("target_repo") or "").strip()
    target_url = str(payload.get("target_url") or "").strip()
    parsed_repo = layer0.parse_repo(target_repo) or layer0.parse_repo(target_url)
    url = _normalize_url(target_url, parsed_repo)

    tool_id = _resolve_tool_id(payload, parsed_repo, roster)
    if not tool_id:
        return _error_response("缺少可辨識的 tool_id、target_repo 或 target_url", decision=decision)

    decided_date = _normalize_date(payload.get("decided_at"), fallback=today)
    decision_note = str(payload.get("decision_note") or "").strip()
    trigger_when = str(payload.get("trigger_when") or "").strip()
    source_item_id = str(payload.get("source_item_id") or "").strip()
    eval_id = str(payload.get("eval_id") or "").strip()

    card_path = data_path / "tools" / f"{tool_id}.yaml"
    existing_card = validate.load_yaml(card_path) if card_path.is_file() else None
    tool_name = (
        str(payload.get("tool_name") or "").strip()
        or (existing_card.get("name") if existing_card else "")
        or parsed_repo
        or tool_id
    )

    extra_slots = _valid_slots(payload.get("slots"), roster)
    base_slots = _valid_slots((existing_card or {}).get("slots"), roster)
    merged_slots = list(dict.fromkeys(base_slots + extra_slots))

    written_files = []
    meta_tag = " / ".join(filter(None, [f"eval:{eval_id}" if eval_id else "", f"item:{source_item_id}" if source_item_id else ""]))
    meta_suffix = f"（{meta_tag}）" if meta_tag else ""

    if decision == "approve_l2":
        req_doc, valid_slot = _build_layer2_request(tool_id, payload, existing_card, roster, funnel_path)
        if valid_slot and valid_slot not in merged_slots:
            merged_slots.append(valid_slot)

        # 建立或更新待測工具卡（保留既有狀態若已是 default/trial，新卡寫 pending）
        if existing_card:
            card = dict(existing_card)
            card["slots"] = merged_slots
            if url and not card.get("url"):
                card["url"] = url
            card["sources"] = _merge_sources(card.get("sources"), source_item_id)
            card["notes"] = _append_note(
                card.get("notes"),
                f"{decided_date} OmniKeep 核准進第 2 層實測{meta_suffix}：{decision_note or '待桌機隔離驗證'}",
            )
        else:
            card = {
                "id": tool_id,
                "name": tool_name,
                "slots": merged_slots,
                "status": "pending",
                **({"url": url} if url else {}),
                "sources": _merge_sources([], source_item_id),
                "notes": f"{decided_date} OmniKeep 核准進第 2 層實測{meta_suffix}：{decision_note or '待桌機隔離驗證'}",
                "added": decided_date,
            }
        _write_yaml(card_path, card)
        written_files.append(str(card_path))

        req_path = funnel_path / "layer2-requests" / f"{tool_id}.json"
        _write_json(req_path, req_doc)
        written_files.append(str(req_path))

        todo_path = funnel_path / "layer2-todo.md"
        req_rel = f"data/funnel/layer2-requests/{tool_id}.json"
        _upsert_layer2_todo(todo_path, tool_id, req_doc, req_rel, note=decision_note)
        written_files.append(str(todo_path))

        post_errors, _ = validate.check(data_path, state=state_dir)
        if post_errors:
            return _error_response(f"寫入後名冊驗證失敗：{'；'.join(post_errors[:3])}", decision=decision, tool_id=tool_id)

        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ok",
            "decision": decision,
            "tool_id": tool_id,
            "card_path": str(card_path),
            "layer2_request_path": str(req_path),
            "layer2_todo_path": str(todo_path),
            "layer2_request": req_doc,
            "written_files": written_files,
            "error": "",
        }

    if decision == "on_demand":
        effective_trigger = trigger_when or decision_note or "依特定情境按需召喚（OmniKeep 拍板，不常駐）"
        effective_reason = decision_note or f"按需備案（Progressive Disclosure）：{effective_trigger}"
        card = dict(existing_card or {})
        card.update({
            "id": tool_id,
            "name": tool_name,
            "slots": merged_slots,
            "status": "on_demand",
            "trigger_when": effective_trigger,
            "decided_at": decided_date,
            "reason": effective_reason,
            "sources": _merge_sources(card.get("sources"), source_item_id),
            "added": card.get("added") or decided_date,
        })
        if url:
            card["url"] = url
        # on_demand 嚴格維持 0 token 常駐：不掛 plugin，不進 marketplace、規則或 MCP
        card.pop("trial_until", None)
        card["notes"] = _append_note(
            card.get("notes"),
            f"{decided_date} OmniKeep 收為按需備案{meta_suffix}；觸發條件：{effective_trigger}",
        )
        _write_yaml(card_path, card)
        written_files.append(str(card_path))

        post_errors, _ = validate.check(data_path, state=state_dir)
        if post_errors:
            return _error_response(f"寫入後名冊驗證失敗：{'；'.join(post_errors[:3])}", decision=decision, tool_id=tool_id)

        return {
            "schema_version": SCHEMA_VERSION,
            "status": "ok",
            "decision": decision,
            "tool_id": tool_id,
            "card_path": str(card_path),
            "trigger_when": effective_trigger,
            "resident_tokens": 0,
            "written_files": written_files,
            "error": "",
        }

    # decision == "reject"
    effective_reason = decision_note or "OmniKeep 拍板拒絕（不納入 OmniKit 名冊）"
    card = dict(existing_card or {})
    card.update({
        "id": tool_id,
        "name": tool_name,
        "slots": merged_slots,
        "status": "rejected",
        "decided_at": decided_date,
        "reason": effective_reason,
        "sources": _merge_sources(card.get("sources"), source_item_id),
        "added": card.get("added") or decided_date,
    })
    if url:
        card["url"] = url
    card.pop("trial_until", None)
    card.pop("trigger_when", None)
    repo_hint = f"repo: {parsed_repo}。" if parsed_repo else ""
    card["notes"] = _append_note(
        card.get("notes"),
        f"{decided_date} OmniKeep 拒絕{meta_suffix}：{repo_hint}{effective_reason}",
    )
    _write_yaml(card_path, card)
    written_files.append(str(card_path))

    history_path = funnel_path / "rejected-history.jsonl"
    history_entry = {
        "tool_id": tool_id,
        "name": tool_name,
        "repo": parsed_repo or "",
        "url": url,
        "slots": merged_slots,
        "reason": effective_reason,
        "decision_note": decision_note,
        "source_item_id": source_item_id,
        "eval_id": eval_id,
        "decided_at": str(payload.get("decided_at") or decided_date),
    }
    _upsert_rejected_history(history_path, history_entry)
    written_files.append(str(history_path))

    post_errors, _ = validate.check(data_path, state=state_dir)
    if post_errors:
        return _error_response(f"寫入後名冊驗證失敗：{'；'.join(post_errors[:3])}", decision=decision, tool_id=tool_id)

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok",
        "decision": decision,
        "tool_id": tool_id,
        "card_path": str(card_path),
        "rejected_history_path": str(history_path),
        "written_files": written_files,
        "error": "",
    }


def selftest():
    checks = []

    def check(name, ok):
        checks.append((name, bool(ok)))

    tmp = Path(tempfile.mkdtemp(prefix="okrec-"))
    try:
        data_copy = tmp / "data"
        shutil.copytree(_omnikit.ROOT / "data", data_copy)
        state_dir = tmp / "state"

        # 1. approve_l2
        r_l2 = record_decision(
            {
                "schema_version": "1.0",
                "tool_id": "fast-anything",
                "target_repo": "EL4CTEO/fast-anything",
                "target_url": "https://github.com/EL4CTEO/fast-anything",
                "decision": "approve_l2",
                "decision_note": "驗證 Windows 相容性與速度",
                "source_item_id": "item-l2",
                "eval_id": "eval-1",
                "decided_at": "2026-11-24T01:00:00Z",
                "slots": ["browser"],
            },
            data_dir=data_copy,
            state_dir=state_dir,
        )
        req_file = Path(r_l2["layer2_request_path"])
        check("approve_l2 成功並產出合法 layer2-request JSON",
              r_l2["status"] == "ok" and req_file.is_file()
              and not list(_layer2_request_validator().iter_errors(json.loads(req_file.read_text(encoding="utf-8")))))
        check("approve_l2 登記 layer2-todo.md",
              "fast-anything" in Path(r_l2["layer2_todo_path"]).read_text(encoding="utf-8"))

        # 2. on_demand
        r_od = record_decision(
            {
                "schema_version": "1.0",
                "tool_id": "niche-parser",
                "target_repo": "acme/niche-parser",
                "target_url": "https://github.com/acme/niche-parser",
                "decision": "on_demand",
                "decision_note": "偶爾處理大型二進位檔時使用",
                "trigger_when": "處理超過 50MB 的大型專屬格式檔案時召回",
                "source_item_id": "item-od",
                "eval_id": "eval-2",
                "decided_at": "2026-11-24",
            },
            data_dir=data_copy,
            state_dir=state_dir,
        )
        od_card = validate.load_yaml(Path(r_od["card_path"]))
        check("on_demand 寫入名冊含 status=on_demand 與 trigger_when",
              r_od["status"] == "ok" and od_card["status"] == "on_demand"
              and od_card["trigger_when"] == "處理超過 50MB 的大型專屬格式檔案時召回"
              and r_od["resident_tokens"] == 0)

        # 3. reject + layer0 similar_rejected 命中驗證
        r_rej = record_decision(
            {
                "schema_version": "1.0",
                "tool_id": "noisy-wrapper",
                "target_repo": "acme/noisy-wrapper",
                "target_url": "https://github.com/acme/noisy-wrapper",
                "decision": "reject",
                "decision_note": "只是包一層薄 CLI 且社群回報常限流",
                "source_item_id": "item-rej",
                "eval_id": "eval-3",
                "decided_at": "2026-11-24",
            },
            data_dir=data_copy,
            state_dir=state_dir,
        )
        errs, updated_roster = validate.check(data_copy, state=state_dir)
        hits_same = layer0.similar_rejected(
            "acme/noisy-wrapper",
            "unrelated short text",
            updated_roster,
            history_path=data_copy / "funnel" / "rejected-history.jsonl",
        )
        check("reject 寫入拒絕歷史且名冊驗證通過",
              r_rej["status"] == "ok" and not errs and Path(r_rej["rejected_history_path"]).is_file())
        check("下次 layer0 遇見同 repo 命中 similar_rejected",
              bool(hits_same) and hits_same[0]["id"] == "noisy-wrapper" and hits_same[0]["similarity"] == 1.0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'✓' if ok else '✗'} {name}")
    print(f"record_decision 自我測試：{len(checks) - len(failed)}/{len(checks)} 通過")
    return 1 if failed else 0


def main(argv=None):
    _omnikit.utf8_stdio()
    parser = argparse.ArgumentParser(description="OmniKit 拍板回寫 CLI")
    parser.add_argument("--health", action="store_true", help="印出健康狀態 JSON 並以 0 結束")
    parser.add_argument("--version", action="store_true", help="印出版本 JSON 並以 0 結束")
    parser.add_argument("--data", type=Path, help="資料目錄（預設為 repo 的 data/）")
    parser.add_argument("--selftest", action="store_true", help="執行離線自我測試")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.version:
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "status": "ok",
            "tool": "omnikit-record-decision",
            "version": CLI_VERSION,
        }, ensure_ascii=False))
        return 0
    if args.health:
        print(json.dumps(_health_doc(args.data), ensure_ascii=False))
        return 0

    raw = sys.stdin.read()
    if not raw.strip():
        doc = _error_response("stdin 為空，未收到拍板請求 JSON")
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
        result = record_decision(payload, data_dir=args.data)
    except Exception as e:
        _log(f"未預期錯誤：{e}")
        result = _error_response(f"執行拍板回寫時發生錯誤：{e}")

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
