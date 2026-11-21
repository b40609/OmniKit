"""Policy-based model and thinking-level resolver."""

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Any


def _find_catalog_item(
    catalog: list[dict[str, Any]],
    provider_id: str | None,
    model_id: str,
) -> dict[str, Any] | None:
    for item in catalog:
        if item.get("provider_id") == provider_id and item.get("model_id") == model_id:
            return item
    return None


def _matches_candidate(
    item: dict[str, Any],
    candidate: dict[str, Any],
    thinking: str | None,
) -> bool:
    if not item.get("enabled", False):
        return False

    cand_provider = candidate.get("provider_id")
    if cand_provider is not None and item.get("provider_id") != cand_provider:
        return False

    model_id = str(item.get("model_id", ""))
    pattern = candidate.get("model_pattern") or "*"
    if not fnmatchcase(model_id, pattern):
        return False

    exclude_patterns = candidate.get("exclude_patterns") or []
    for excl in exclude_patterns:
        if fnmatchcase(model_id, excl):
            return False

    thinking_values = item.get("thinking_values") or []
    if thinking_values and thinking not in thinking_values:
        return False

    return True


def resolve_role(
    role_name: str,
    policy: dict[str, Any],
    catalog: list[dict[str, Any]],
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a role to a concrete (provider_id, model_id, thinking) using policy and catalog."""
    roles = policy.get("roles") or {}
    if role_name not in roles:
        return {
            "ok": False,
            "reason": "unknown_role",
            "error": f"Unknown role: {role_name}",
        }

    role = roles[role_name] or {}
    forbid_thinking = set(role.get("forbid_thinking") or [])

    if overrides and role_name in overrides and overrides[role_name] is not None:
        override = overrides[role_name]
        provider_id = override.get("provider_id")
        model_id = override.get("model_id")
        thinking = override.get("thinking")

        if thinking in forbid_thinking:
            return {
                "ok": False,
                "reason": "forbidden_thinking",
                "error": f"Thinking level '{thinking}' is forbidden for role '{role_name}'.",
            }

        item = _find_catalog_item(catalog, provider_id, str(model_id))
        if item is None or not item.get("enabled", False):
            return {
                "ok": False,
                "reason": "override_unavailable",
                "error": f"Override model '{provider_id}:{model_id}' is unavailable or disabled.",
            }

        thinking_values = item.get("thinking_values") or []
        if thinking_values and thinking not in thinking_values:
            return {
                "ok": False,
                "reason": "unsupported_thinking",
                "error": (
                    f"Thinking level '{thinking}' is not supported by "
                    f"'{provider_id}:{model_id}' (supported: {thinking_values})."
                ),
            }

        return {
            "ok": True,
            "provider_id": item.get("provider_id"),
            "model_id": item["model_id"],
            "thinking": thinking,
            "thinking_param": item.get("thinking_param"),
            "matched_by": "override",
            "fallback_index": -1,
        }

    tried: list[dict[str, Any]] = []
    candidates = role.get("candidates") or []
    for idx, candidate in enumerate(candidates):
        thinking = candidate.get("thinking")
        if thinking in forbid_thinking:
            tried.append(
                {
                    "index": idx,
                    "candidate": candidate,
                    "reason": "forbidden_thinking",
                }
            )
            continue

        matched = [
            item
            for item in catalog
            if _matches_candidate(item, candidate, thinking)
        ]
        if not matched:
            tried.append(
                {
                    "index": idx,
                    "candidate": candidate,
                    "reason": "no_matching_model",
                }
            )
            continue

        prefer_order = candidate.get("prefer_order") or []
        prefer_rank = {model_id: rank for rank, model_id in enumerate(prefer_order)}

        matched.sort(
            key=lambda item: (
                0 if item["model_id"] in prefer_rank else 1,
                prefer_rank.get(item["model_id"], 0),
                item["model_id"],
                item.get("provider_id") or "",
            )
        )
        chosen = matched[0]
        return {
            "ok": True,
            "provider_id": chosen.get("provider_id"),
            "model_id": chosen["model_id"],
            "thinking": thinking,
            "thinking_param": chosen.get("thinking_param"),
            "matched_by": "policy",
            "fallback_index": idx,
        }

    return {
        "ok": False,
        "reason": "no_candidate_available",
        "error": f"No available candidate matched role '{role_name}'.",
        "tried": tried,
    }
