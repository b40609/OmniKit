"""Model catalog parsing and diffing utilities."""

from __future__ import annotations

from typing import Any

_THINKING_OPTION_IDS = ("effort", "thinking_level")
_AGY_THINKING_SUFFIXES = ("xhigh", "medium", "high", "low", "max")
_DIFF_FIELDS = ("enabled", "thinking_values", "default_thinking")


def _provider_is_enabled(provider: dict[str, Any]) -> bool:
    if not bool(provider.get("canRunChildTask")):
        return False
    constraints = provider.get("constraints") or []
    for constraint in constraints:
        if "disabled" in str(constraint).lower():
            return False
    return True


def _extract_thinking_option(model: dict[str, Any]) -> tuple[str | None, list[str], str | None]:
    options = model.get("options") or []
    for opt in options:
        if not isinstance(opt, dict):
            continue
        opt_id = opt.get("id")
        if opt_id in _THINKING_OPTION_IDS:
            raw_values = opt.get("values") or []
            values = [str(v) for v in raw_values]
            default_val = opt.get("default")
            return str(opt_id), values, (str(default_val) if default_val is not None else None)
    return None, [], None


def parse_t3_capabilities(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse T3 orchestrator_capabilities JSON into normalized catalog items."""
    items: list[dict[str, Any]] = []
    providers = data.get("providers") or []
    for provider in providers:
        provider_id = provider["providerInstanceId"]
        driver = provider["driverKind"]
        enabled = _provider_is_enabled(provider)
        for model in provider.get("models") or []:
            model_id = model["id"]
            label = model.get("label") or model_id
            thinking_param, thinking_values, default_thinking = _extract_thinking_option(model)
            items.append(
                {
                    "source": "t3",
                    "provider_id": provider_id,
                    "driver": driver,
                    "enabled": enabled,
                    "model_id": model_id,
                    "label": label,
                    "thinking_param": thinking_param,
                    "thinking_values": thinking_values,
                    "default_thinking": default_thinking,
                }
            )
    return items


def parse_agy_models(text: str) -> list[dict[str, Any]]:
    """Parse plain-text output from `agy models` into catalog items."""
    items: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "\t" not in line:
            continue
        model_id, label = line.split("\t", 1)
        model_id = model_id.strip()
        label = label.strip()
        if not model_id:
            continue

        base_model = model_id
        thinking_suffix: str | None = None
        for suffix in _AGY_THINKING_SUFFIXES:
            token = f"-{suffix}"
            if model_id.endswith(token) and len(model_id) > len(token):
                base_model = model_id[: -len(token)]
                thinking_suffix = suffix
                break

        items.append(
            {
                "source": "agy",
                "model_id": model_id,
                "label": label or model_id,
                "base_model": base_model,
                "thinking_suffix": thinking_suffix,
            }
        )
    return items


def _catalog_key(item: dict[str, Any]) -> tuple[str, str]:
    owner = item.get("provider_id") or item.get("source") or ""
    return (str(owner), str(item["model_id"]))


def diff_catalogs(
    old_items: list[dict[str, Any]],
    new_items: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Compare two catalog item lists and return added, removed, and changed entries."""
    old_map = {_catalog_key(item): item for item in old_items}
    new_map = {_catalog_key(item): item for item in new_items}

    added_keys = sorted(new_map.keys() - old_map.keys())
    removed_keys = sorted(old_map.keys() - new_map.keys())
    common_keys = sorted(old_map.keys() & new_map.keys())

    added = [new_map[key] for key in added_keys]
    removed = [old_map[key] for key in removed_keys]
    changed: list[dict[str, Any]] = []

    for key in common_keys:
        old_item = old_map[key]
        new_item = new_map[key]
        diff_fields = [
            field
            for field in _DIFF_FIELDS
            if old_item.get(field) != new_item.get(field)
        ]
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
