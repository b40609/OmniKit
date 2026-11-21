"""Role-based model and thinking-level resolver (stdlib only)."""

from __future__ import annotations

import fnmatch
from typing import Any


def _resolve_override(
    role_name: str,
    override: dict[str, Any],
    forbid_thinking: set[str],
    catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate and apply an explicit role override without silent fallback."""
    ov_provider = override.get("provider_id")
    ov_model = override.get("model_id")
    ov_thinking = override.get("thinking")

    if ov_thinking in forbid_thinking:
        return {
            "ok": False,
            "reason": "forbidden_thinking",
            "error": (
                f"Override thinking '{ov_thinking}' is forbidden for role '{role_name}'."
            ),
        }

    matched_item = next(
        (
            item
            for item in catalog
            if item.get("provider_id") == ov_provider and item.get("model_id") == ov_model
        ),
        None,
    )
    if matched_item is None or not matched_item.get("enabled"):
        return {
            "ok": False,
            "reason": "override_unavailable",
            "error": (
                f"Override target '{ov_provider}:{ov_model}' is missing or disabled."
            ),
        }

    thinking_values = matched_item.get("thinking_values") or []
    if thinking_values and ov_thinking not in thinking_values:
        return {
            "ok": False,
            "reason": "unsupported_thinking",
            "error": (
                f"Thinking '{ov_thinking}' is not supported by '{ov_provider}:{ov_model}' "
                f"(supported: {thinking_values})."
            ),
        }

    return {
        "ok": True,
        "provider_id": matched_item.get("provider_id"),
        "model_id": matched_item["model_id"],
        "thinking": ov_thinking,
        "thinking_param": matched_item.get("thinking_param"),
        "matched_by": "override",
        "fallback_index": -1,
    }


def _matches_candidate(item: dict[str, Any], candidate: dict[str, Any]) -> bool:
    """Return True if a catalog entry satisfies a policy candidate filter."""
    if item.get("enabled") is not True:
        return False

    cand_provider = candidate.get("provider_id")
    if cand_provider and item.get("provider_id") != cand_provider:
        return False

    model_id = str(item["model_id"])
    pattern = candidate.get("model_pattern", "*")
    if not fnmatch.fnmatchcase(model_id, pattern):
        return False

    for exclude_pat in candidate.get("exclude_patterns") or []:
        if fnmatch.fnmatchcase(model_id, exclude_pat):
            return False

    thinking_values = item.get("thinking_values") or []
    cand_thinking = candidate.get("thinking")
    if thinking_values and cand_thinking not in thinking_values:
        return False

    return True


def resolve_role(
    role_name: str,
    policy: dict[str, Any],
    catalog: list[dict[str, Any]],
    overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve a role name against policy candidates (or explicit overrides) and catalog."""
    roles = policy.get("roles") or {}
    if role_name not in roles:
        return {
            "ok": False,
            "reason": "unknown_role",
            "error": f"Unknown role: {role_name}",
        }

    role = roles[role_name]
    forbid_thinking = set(role.get("forbid_thinking") or [])

    if overrides is not None and role_name in overrides and overrides[role_name] is not None:
        return _resolve_override(role_name, overrides[role_name], forbid_thinking, catalog)

    tried: list[dict[str, Any]] = []
    for idx, candidate in enumerate(role.get("candidates") or []):
        cand_thinking = candidate.get("thinking")
        if cand_thinking in forbid_thinking:
            tried.append(
                {
                    "index": idx,
                    "candidate": candidate,
                    "reason": "forbidden_thinking",
                }
            )
            continue

        matches = [item for item in catalog if _matches_candidate(item, candidate)]
        if not matches:
            tried.append(
                {
                    "index": idx,
                    "candidate": candidate,
                    "reason": "no_matching_model",
                }
            )
            continue

        prefer_order = candidate.get("prefer_order") or []
        rank = {model_id: pos for pos, model_id in enumerate(prefer_order)}
        matches.sort(
            key=lambda item: (
                rank.get(item["model_id"], len(prefer_order)),
                item["model_id"],
                item.get("provider_id") or "",
            )
        )
        chosen = matches[0]
        return {
            "ok": True,
            "provider_id": chosen.get("provider_id"),
            "model_id": chosen["model_id"],
            "thinking": cand_thinking,
            "thinking_param": chosen.get("thinking_param"),
            "matched_by": "policy",
            "fallback_index": idx,
        }

    return {
        "ok": False,
        "reason": "no_candidate_available",
        "error": f"No available candidate matched for role '{role_name}'.",
        "tried": tried,
    }
