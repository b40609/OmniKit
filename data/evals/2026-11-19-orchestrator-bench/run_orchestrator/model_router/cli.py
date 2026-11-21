"""CLI entrypoint for `python -m model_router.cli`."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .catalog import diff_catalogs, parse_agy_models, parse_t3_capabilities
from .resolver import resolve_role


def _load_json(path: str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _load_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _cmd_catalog(args: argparse.Namespace) -> int:
    items = parse_t3_capabilities(_load_json(args.t3))
    if args.agy:
        items.extend(parse_agy_models(_load_text(args.agy)))

    if args.json:
        _print_json(items)
    else:
        for item in items:
            scope = item.get("provider_id") or item.get("source")
            print(f"[{scope}] {item['model_id']} ({item['label']})")
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    old_items = parse_t3_capabilities(_load_json(args.old))
    new_items = parse_t3_capabilities(_load_json(args.new))
    result = diff_catalogs(old_items, new_items)

    if args.json:
        _print_json(result)
    else:
        print(
            f"added={len(result['added'])} "
            f"removed={len(result['removed'])} "
            f"changed={len(result['changed'])}"
        )
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    overrides: dict[str, dict[str, Any]] | None = None
    if args.override is not None:
        parts = args.override.split(":", 2)
        if len(parts) != 3 or not parts[0] or not parts[1]:
            err_result = {
                "ok": False,
                "reason": "invalid_override_format",
                "error": (
                    f"Invalid --override '{args.override}'; "
                    "expected <provider_id:model_id:thinking>."
                ),
            }
            _print_json(err_result)
            return 2
        overrides = {
            args.role: {
                "provider_id": parts[0],
                "model_id": parts[1],
                "thinking": parts[2],
            }
        }

    policy = _load_json(args.policy)
    catalog = parse_t3_capabilities(_load_json(args.t3))
    result = resolve_role(args.role, policy, catalog, overrides=overrides)

    if args.json or not result["ok"]:
        _print_json(result)
    else:
        print(
            f"{result['provider_id']}:{result['model_id']} "
            f"({result['thinking_param']}={result['thinking']}, "
            f"matched_by={result['matched_by']}, "
            f"fallback_index={result['fallback_index']})"
        )
    return 0 if result["ok"] else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="model_router.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_catalog = subparsers.add_parser("catalog", help="Parse T3 and optional agy catalogs")
    p_catalog.add_argument("--t3", required=True, help="Path to T3 capabilities JSON")
    p_catalog.add_argument("--agy", required=False, help="Path to agy models text output")
    p_catalog.add_argument("--json", action="store_true", help="Output JSON to stdout")
    p_catalog.set_defaults(func=_cmd_catalog)

    p_diff = subparsers.add_parser("diff", help="Diff two T3 capabilities JSON files")
    p_diff.add_argument("--old", required=True, help="Path to old T3 capabilities JSON")
    p_diff.add_argument("--new", required=True, help="Path to new T3 capabilities JSON")
    p_diff.add_argument("--json", action="store_true", help="Output JSON to stdout")
    p_diff.set_defaults(func=_cmd_diff)

    p_resolve = subparsers.add_parser("resolve", help="Resolve a role against policy and catalog")
    p_resolve.add_argument("--role", required=True, help="Role name to resolve")
    p_resolve.add_argument("--policy", required=True, help="Path to policy JSON")
    p_resolve.add_argument("--t3", required=True, help="Path to T3 capabilities JSON")
    p_resolve.add_argument(
        "--override",
        required=False,
        help="Override in <provider_id:model_id:thinking> format",
    )
    p_resolve.add_argument("--json", action="store_true", help="Output JSON to stdout")
    p_resolve.set_defaults(func=_cmd_resolve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
