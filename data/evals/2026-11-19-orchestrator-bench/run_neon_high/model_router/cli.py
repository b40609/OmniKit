"""Command-line interface for model_router."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .catalog import diff_catalogs, parse_agy_models, parse_t3_capabilities
from .resolver import resolve_role


def _read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _cmd_catalog(args: argparse.Namespace) -> int:
    t3_data = _read_json(args.t3)
    items = parse_t3_capabilities(t3_data)
    if args.agy:
        agy_text = Path(args.agy).read_text(encoding="utf-8")
        items.extend(parse_agy_models(agy_text))

    if args.json:
        _print_json(items)
    else:
        for item in items:
            owner = item.get("provider_id") or item.get("source")
            model_id = item["model_id"]
            if item.get("source") == "t3":
                status = "enabled" if item.get("enabled") else "disabled"
                thinking = ",".join(item.get("thinking_values") or []) or "-"
                print(f"{owner}\t{model_id}\t{status}\t{thinking}")
            else:
                suffix = item.get("thinking_suffix") or "-"
                print(f"{owner}\t{model_id}\t{item.get('base_model')}\t{suffix}")
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    old_items = parse_t3_capabilities(_read_json(args.old))
    new_items = parse_t3_capabilities(_read_json(args.new))
    result = diff_catalogs(old_items, new_items)

    if args.json:
        _print_json(result)
    else:
        print(
            f"added={len(result['added'])} "
            f"removed={len(result['removed'])} "
            f"changed={len(result['changed'])}"
        )
        for item in result["added"]:
            owner = item.get("provider_id") or item.get("source")
            print(f"+ {owner}:{item['model_id']}")
        for item in result["removed"]:
            owner = item.get("provider_id") or item.get("source")
            print(f"- {owner}:{item['model_id']}")
        for entry in result["changed"]:
            key = ":".join(entry["key"])
            fields = ",".join(entry["changes"])
            print(f"~ {key} ({fields})")
    return 0


def _parse_override(role_name: str, raw_override: str) -> dict[str, dict[str, Any]]:
    parts = raw_override.split(":", 2)
    if len(parts) != 3 or not parts[0] or not parts[1]:
        raise ValueError(
            f"Invalid --override format '{raw_override}'; expected <provider_id:model_id:thinking>."
        )
    provider_id, model_id, thinking = parts
    return {
        role_name: {
            "provider_id": provider_id,
            "model_id": model_id,
            "thinking": thinking if thinking != "" else None,
        }
    }


def _cmd_resolve(args: argparse.Namespace) -> int:
    policy = _read_json(args.policy)
    catalog = parse_t3_capabilities(_read_json(args.t3))
    overrides: dict[str, Any] | None = None
    if args.override is not None:
        try:
            overrides = _parse_override(args.role, args.override)
        except ValueError as exc:
            result = {
                "ok": False,
                "reason": "invalid_override",
                "error": str(exc),
            }
            _print_json(result)
            return 2

    result = resolve_role(args.role, policy, catalog, overrides=overrides)
    if args.json or not result.get("ok"):
        _print_json(result)
    else:
        thinking = result.get("thinking")
        param = result.get("thinking_param") or "thinking"
        print(
            f"{result['provider_id']}:{result['model_id']} "
            f"({param}={thinking}, matched_by={result['matched_by']}, "
            f"fallback_index={result['fallback_index']})"
        )
    return 0 if result.get("ok") else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="model_router.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_catalog = subparsers.add_parser("catalog", help="Parse T3 and optional AGY model catalogs.")
    p_catalog.add_argument("--t3", required=True, help="Path to T3 capabilities JSON file.")
    p_catalog.add_argument("--agy", help="Optional path to `agy models` text output file.")
    p_catalog.add_argument("--json", action="store_true", help="Output result as JSON.")
    p_catalog.set_defaults(func=_cmd_catalog)

    p_diff = subparsers.add_parser("diff", help="Diff two T3 capabilities JSON files.")
    p_diff.add_argument("--old", required=True, help="Path to old T3 capabilities JSON file.")
    p_diff.add_argument("--new", required=True, help="Path to new T3 capabilities JSON file.")
    p_diff.add_argument("--json", action="store_true", help="Output result as JSON.")
    p_diff.set_defaults(func=_cmd_diff)

    p_resolve = subparsers.add_parser("resolve", help="Resolve a role against policy and catalog.")
    p_resolve.add_argument("--role", required=True, help="Role name to resolve.")
    p_resolve.add_argument("--policy", required=True, help="Path to policy JSON file.")
    p_resolve.add_argument("--t3", required=True, help="Path to T3 capabilities JSON file.")
    p_resolve.add_argument(
        "--override",
        help="Override in format <provider_id:model_id:thinking>.",
    )
    p_resolve.add_argument("--json", action="store_true", help="Output result as JSON.")
    p_resolve.set_defaults(func=_cmd_resolve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
