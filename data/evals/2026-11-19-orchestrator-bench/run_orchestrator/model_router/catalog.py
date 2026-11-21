"""Model catalog parsing and diffing utilities (stdlib only)."""

from __future__ import annotations

from typing import Any

_THINKING_SUFFIXES = ("-xhigh", "-high", "-medium", "-low", "-max")
_THINKING_OPTION_IDS = ("effort", "thinking_level")
_DIFF_FIELDS = ("enabled", "thinking_values", "default_thinking")


def _extract_thinking_option(options: list[dict[str, Any]]) -> tuple[str | None, list[str], str | None]:
    """Return (thinking_param, thinking_values, default_thinking) from model options."""
    for opt in options:
        opt_id = opt.get("id")
        if opt_id in _THINKING_OPTION_IDS:
            values = [str(v) for v in (opt.get("values") or [])]
            default_val = opt.get("default")
            return (
                opt_id,
                values,
                str(default_val) if default_val is not None else None,
            )
    return None, [], None


def parse_t3_capabilities(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse T3 orchestrator_capabilities JSON dict into normalized catalog entries."""
    items: list[dict[str, Any]] = []
    for provider in data.get("providers") or []:
        constraints = provider.get("constraints") or []
        has_disabled_constraint = any("disabled" in str(c).lower() for c in constraints)
        enabled = bool(provider.get("canRunChildTask")) and not has_disabled_constraint
        provider_id = provider["providerInstanceId"]
        driver = provider["driverKind"]

        for model in provider.get("models") or []:
            model_id = model["id"]
            thinking_param, thinking_values, default_thinking = _extract_thinking_option(
                model.get("options") or []
            )
            items.append(
                {
                    "source": "t3",
                    "provider_id": provider_id,
                    "driver": driver,
                    "enabled": enabled,
                    "model_id": model_id,
                    "label": model.get("label") or model_id,
                    "thinking_param": thinking_param,
                    "thinking_values": thinking_values,
                    "default_thinking": default_thinking,
                }
            )
    return items


def parse_agy_models(text: str) -> list[dict[str, Any]]:
    """Parse plain-text output of `agy models` into normalized entries."""
    items: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip() or "\t" not in line:
            continue
        raw_id, raw_label = line.split("\t", 1)
        model_id = raw_id.strip()
        if not model_id:
            continue
        label = raw_label.strip()

        base_model = model_id
        thinking_suffix: str | None = None
        for suffix in _THINKING_SUFFIXES:
            if model_id.endswith(suffix) and len(model_id) > len(suffix):
                base_model = model_id[: -len(suffix)]
                thinking_suffix = suffix[1:]
                break

        items.append(
            {
                "source": "agy",
                "model_id": model_id,
                "label": label,
                "base_model": base_model,
                "thinking_suffix": thinking_suffix,
            }
        )
    return items


def _catalog_key(item: dict[str, Any]) -> tuple[str, str]:
    """Build deterministic (provider_or_source, model_id) index key."""
    scope = str(item.get("provider_id") or item.get("source") or "")
    return (scope, str(item["model_id"]))


def diff_catalogs(old_items: list[dict[str, Any]], new_items: list[dict[str, Any]]) -> dict[str, list[Any]]:
    """Compute sorted added, removed, and changed entries between two catalog lists."""
    old_map = {_catalog_key(item): item for item in old_items}
    new_map = {_catalog_key(item): item for item in new_items}

    old_keys = set(old_map)
    new_keys = set(new_map)

    added = [new_map[k] for k in sorted(new_keys - old_keys)]
    removed = [old_map[k] for k in sorted(old_keys - new_keys)]
    changed: list[dict[str, Any]] = []

    for key in sorted(old_keys & new_keys):
        old_item = old_map[key]
        new_item = new_map[key]
        diff_fields = [field for field in _DIFF_FIELDS if old_item.get(field) != new_item.get(field)]
        if diff_fields:
            changed.append(
                {
                    "key": [key[0], key[1]],
                    "old": old_item,
                    "new": new_item,
                    "changes": diff_fields,
                }
            )

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
    }
