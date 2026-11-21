"""Unit tests for model_router package and CLI."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import model_router
from model_router import (
    diff_catalogs,
    parse_agy_models,
    parse_t3_capabilities,
    resolve_role,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = ROOT_DIR / "fixtures"
T3_FIXTURE = FIXTURES_DIR / "t3_caps.json"
AGY_FIXTURE = FIXTURES_DIR / "agy_models.txt"


def _load_t3_fixture() -> dict:
    return json.loads(T3_FIXTURE.read_text(encoding="utf-8"))


class TestCatalog(unittest.TestCase):
    def test_package_exports(self) -> None:
        self.assertTrue(callable(model_router.parse_t3_capabilities))
        self.assertTrue(callable(model_router.parse_agy_models))
        self.assertTrue(callable(model_router.diff_catalogs))
        self.assertTrue(callable(model_router.resolve_role))

    def test_parse_t3_capabilities_fixture(self) -> None:
        items = parse_t3_capabilities(_load_t3_fixture())
        self.assertEqual(len(items), 8)

        by_key = {(item["provider_id"], item["model_id"]): item for item in items}

        grok = by_key[("grok", "grok-build")]
        self.assertEqual(grok["source"], "t3")
        self.assertEqual(grok["driver"], "grok")
        self.assertFalse(grok["enabled"])
        self.assertIsNone(grok["thinking_param"])
        self.assertEqual(grok["thinking_values"], [])
        self.assertIsNone(grok["default_thinking"])

        claude_opus = by_key[("claudeAgent", "claude-opus-5-5")]
        self.assertTrue(claude_opus["enabled"])
        self.assertEqual(claude_opus["thinking_param"], "effort")
        self.assertIn("ultrathink", claude_opus["thinking_values"])
        self.assertEqual(claude_opus["default_thinking"], "medium")

        neon = by_key[("antigravity", "gemini-4-neon")]
        self.assertTrue(neon["enabled"])
        self.assertEqual(neon["thinking_param"], "thinking_level")
        self.assertEqual(neon["thinking_values"], ["low", "medium", "high", "xhigh"])
        self.assertEqual(neon["default_thinking"], "high")

    def test_parse_t3_disabled_constraint_case_insensitive_and_label_fallback(self) -> None:
        data = {
            "providers": [
                {
                    "providerInstanceId": "custom",
                    "driverKind": "customDriver",
                    "canRunChildTask": True,
                    "constraints": ["Temporarily DISABLED by quota"],
                    "models": [{"id": "m-1"}],
                }
            ]
        }
        items = parse_t3_capabilities(data)
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0]["enabled"])
        self.assertEqual(items[0]["label"], "m-1")

    def test_parse_agy_models_fixture_and_suffixes(self) -> None:
        text = AGY_FIXTURE.read_text(encoding="utf-8") + "\ncustom-low\tCustom Low\ncustom-max\tCustom Max\n\nno-tab-line\n"
        items = parse_agy_models(text)
        self.assertEqual(len(items), 10)

        by_id = {item["model_id"]: item for item in items}
        self.assertEqual(by_id["gemini-4-neon-high"]["base_model"], "gemini-4-neon")
        self.assertEqual(by_id["gemini-4-neon-high"]["thinking_suffix"], "high")
        self.assertEqual(by_id["gemini-4-neon-xhigh"]["base_model"], "gemini-4-neon")
        self.assertEqual(by_id["gemini-4-neon-xhigh"]["thinking_suffix"], "xhigh")
        self.assertEqual(by_id["claude-opus-5-5-medium"]["base_model"], "claude-opus-5-5")
        self.assertEqual(by_id["claude-opus-5-5-medium"]["thinking_suffix"], "medium")
        self.assertEqual(by_id["custom-low"]["base_model"], "custom")
        self.assertEqual(by_id["custom-low"]["thinking_suffix"], "low")
        self.assertEqual(by_id["custom-max"]["base_model"], "custom")
        self.assertEqual(by_id["custom-max"]["thinking_suffix"], "max")
        self.assertEqual(
            by_id["gemini-pro-orchestrator-neon"]["base_model"],
            "gemini-pro-orchestrator-neon",
        )
        self.assertIsNone(by_id["gemini-pro-orchestrator-neon"]["thinking_suffix"])

    def test_diff_catalogs_added_removed_changed_and_sorting(self) -> None:
        old_items = parse_t3_capabilities(_load_t3_fixture())
        new_raw = copy.deepcopy(_load_t3_fixture())

        # Remove grok-build
        new_raw["providers"][1]["models"] = []
        # Change antigravity/gemini-4-argon thinking_values and default_thinking
        new_raw["providers"][3]["models"][1]["options"][0]["values"].append("xhigh")
        new_raw["providers"][3]["models"][1]["options"][0]["default"] = "xhigh"
        # Change antigravity_ava enabled -> False
        new_raw["providers"][4]["canRunChildTask"] = False
        # Change label only on claude-sonnet-5-5 (should NOT appear in changed)
        new_raw["providers"][2]["models"][1]["label"] = "Sonnet Renamed"
        # Add two new models out of alphabetical order
        new_raw["providers"][3]["models"].append({"id": "gemini-4-z", "label": "Z"})
        new_raw["providers"][2]["models"].append({"id": "claude-haiku-5-5", "label": "Haiku"})

        new_items = parse_t3_capabilities(new_raw)
        diff = diff_catalogs(old_items, new_items)

        self.assertEqual(
            [(x["provider_id"], x["model_id"]) for x in diff["added"]],
            [("antigravity", "gemini-4-z"), ("claudeAgent", "claude-haiku-5-5")],
        )
        self.assertEqual(
            [(x["provider_id"], x["model_id"]) for x in diff["removed"]],
            [("grok", "grok-build")],
        )
        self.assertEqual(
            [c["key"] for c in diff["changed"]],
            [
                ["antigravity", "gemini-4-argon"],
                ["antigravity_ava", "gemini-3.8-flash"],
            ],
        )
        self.assertEqual(diff["changed"][0]["changes"], ["thinking_values", "default_thinking"])
        self.assertEqual(diff["changed"][1]["changes"], ["enabled"])

    def test_diff_catalogs_uses_source_when_no_provider_id(self) -> None:
        old_items = parse_agy_models("a-high\tA High\nb-high\tB High\n")
        new_items = parse_agy_models("b-high\tB High\nc-high\tC High\n")
        diff = diff_catalogs(old_items, new_items)
        self.assertEqual([x["model_id"] for x in diff["added"]], ["c-high"])
        self.assertEqual([x["model_id"] for x in diff["removed"]], ["a-high"])
        self.assertEqual(diff["changed"], [])


class TestResolver(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = parse_t3_capabilities(_load_t3_fixture())
        self.policy = {
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
                        },
                        {
                            "provider_id": "antigravity_ava",
                            "model_pattern": "gemini-*",
                            "thinking": "high",
                        },
                    ],
                },
                "claude-default": {
                    "forbid_thinking": [],
                    "candidates": [
                        {
                            "provider_id": "claudeAgent",
                            "model_pattern": "claude-*",
                            "thinking": "medium",
                        }
                    ],
                },
            }
        }

    def test_resolve_unknown_role(self) -> None:
        res = resolve_role("does-not-exist", self.policy, self.catalog)
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "unknown_role")
        self.assertIn("error", res)

    def test_resolve_policy_prefer_order_and_exclude(self) -> None:
        res = resolve_role("gemini-strong", self.policy, self.catalog)
        self.assertTrue(res["ok"])
        self.assertEqual(res["provider_id"], "antigravity")
        self.assertEqual(res["model_id"], "gemini-4-neon")
        self.assertEqual(res["thinking"], "high")
        self.assertEqual(res["thinking_param"], "thinking_level")
        self.assertEqual(res["matched_by"], "policy")
        self.assertEqual(res["fallback_index"], 0)

    def test_resolve_lexicographical_tiebreaker_outside_prefer_order(self) -> None:
        res = resolve_role("claude-default", self.policy, self.catalog)
        self.assertTrue(res["ok"])
        self.assertEqual(res["model_id"], "claude-opus-5-5")
        self.assertEqual(res["thinking_param"], "effort")

    def test_resolve_skips_forbidden_candidate_and_falls_back(self) -> None:
        policy = {
            "roles": {
                "fallback-test": {
                    "forbid_thinking": ["low", "medium"],
                    "candidates": [
                        {
                            "provider_id": "antigravity",
                            "model_pattern": "gemini-4-*",
                            "thinking": "low",
                        },
                        {
                            "provider_id": "grok",
                            "model_pattern": "grok-*",
                            "thinking": "high",
                        },
                        {
                            "provider_id": "antigravity_ava",
                            "model_pattern": "gemini-3.8-*",
                            "thinking": "high",
                        },
                    ],
                }
            }
        }
        res = resolve_role("fallback-test", policy, self.catalog)
        self.assertTrue(res["ok"])
        self.assertEqual(res["provider_id"], "antigravity_ava")
        self.assertEqual(res["model_id"], "gemini-3.8-flash")
        self.assertEqual(res["fallback_index"], 2)

    def test_resolve_no_candidate_available_records_tried(self) -> None:
        policy = {
            "roles": {
                "impossible": {
                    "forbid_thinking": ["low"],
                    "candidates": [
                        {
                            "provider_id": "antigravity",
                            "model_pattern": "gemini-4-*",
                            "thinking": "low",
                        },
                        {
                            "provider_id": "antigravity_ava",
                            "model_pattern": "gemini-3.8-*",
                            "thinking": "xhigh",
                        },
                    ],
                }
            }
        }
        res = resolve_role("impossible", policy, self.catalog)
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "no_candidate_available")
        self.assertEqual(len(res["tried"]), 2)
        self.assertEqual(res["tried"][0]["reason"], "forbidden_thinking")
        self.assertEqual(res["tried"][1]["reason"], "no_matching_model")

    def test_resolve_override_success(self) -> None:
        overrides = {
            "gemini-strong": {
                "provider_id": "antigravity",
                "model_id": "gemini-4-hydrogen",
                "thinking": "xhigh",
            }
        }
        res = resolve_role("gemini-strong", self.policy, self.catalog, overrides=overrides)
        self.assertTrue(res["ok"])
        self.assertEqual(res["provider_id"], "antigravity")
        self.assertEqual(res["model_id"], "gemini-4-hydrogen")
        self.assertEqual(res["thinking"], "xhigh")
        self.assertEqual(res["thinking_param"], "thinking_level")
        self.assertEqual(res["matched_by"], "override")
        self.assertEqual(res["fallback_index"], -1)

    def test_resolve_override_forbidden_thinking(self) -> None:
        overrides = {
            "gemini-strong": {
                "provider_id": "antigravity",
                "model_id": "gemini-4-neon",
                "thinking": "medium",
            }
        }
        res = resolve_role("gemini-strong", self.policy, self.catalog, overrides=overrides)
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "forbidden_thinking")

    def test_resolve_override_unavailable_disabled_or_missing(self) -> None:
        disabled_override = {
            "claude-default": {
                "provider_id": "grok",
                "model_id": "grok-build",
                "thinking": "high",
            }
        }
        res_disabled = resolve_role(
            "claude-default", self.policy, self.catalog, overrides=disabled_override
        )
        self.assertFalse(res_disabled["ok"])
        self.assertEqual(res_disabled["reason"], "override_unavailable")

        missing_override = {
            "claude-default": {
                "provider_id": "antigravity",
                "model_id": "nonexistent-model",
                "thinking": "high",
            }
        }
        res_missing = resolve_role(
            "claude-default", self.policy, self.catalog, overrides=missing_override
        )
        self.assertFalse(res_missing["ok"])
        self.assertEqual(res_missing["reason"], "override_unavailable")

    def test_resolve_override_unsupported_thinking(self) -> None:
        overrides = {
            "gemini-strong": {
                "provider_id": "antigravity",
                "model_id": "gemini-4-argon",
                "thinking": "xhigh",
            }
        }
        res = resolve_role("gemini-strong", self.policy, self.catalog, overrides=overrides)
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "unsupported_thinking")

    def test_resolve_candidate_without_provider_id_and_model_without_thinking_values(self) -> None:
        catalog = [
            {
                "source": "t3",
                "provider_id": "p2",
                "driver": "custom",
                "enabled": True,
                "model_id": "plain-model",
                "label": "Plain",
                "thinking_param": None,
                "thinking_values": [],
                "default_thinking": None,
            }
        ]
        policy = {
            "roles": {
                "plain": {
                    "forbid_thinking": ["low"],
                    "candidates": [{"model_pattern": "plain-*", "thinking": "high"}],
                }
            }
        }
        res = resolve_role("plain", policy, catalog)
        self.assertTrue(res["ok"])
        self.assertEqual(res["provider_id"], "p2")
        self.assertIsNone(res["thinking_param"])


class TestCLI(unittest.TestCase):
    def _run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "model_router.cli", *args],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_catalog_json_with_t3_and_agy(self) -> None:
        proc = self._run_cli(
            "catalog",
            "--t3",
            str(T3_FIXTURE),
            "--agy",
            str(AGY_FIXTURE),
            "--json",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(len(payload), 16)
        self.assertEqual(sum(1 for x in payload if x["source"] == "t3"), 8)
        self.assertEqual(sum(1 for x in payload if x["source"] == "agy"), 8)

    def test_cli_diff_json(self) -> None:
        modified = copy.deepcopy(_load_t3_fixture())
        modified["providers"][4]["canRunChildTask"] = False
        with tempfile.TemporaryDirectory(dir=ROOT_DIR) as tmpdir:
            new_path = Path(tmpdir) / "new_t3.json"
            new_path.write_text(json.dumps(modified), encoding="utf-8")

            proc = self._run_cli(
                "diff",
                "--old",
                str(T3_FIXTURE),
                "--new",
                str(new_path),
                "--json",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["added"], [])
            self.assertEqual(payload["removed"], [])
            self.assertEqual(len(payload["changed"]), 1)
            self.assertEqual(
                payload["changed"][0]["key"],
                ["antigravity_ava", "gemini-3.8-flash"],
            )

    def test_cli_resolve_success_and_failure_exit_codes(self) -> None:
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
                }
            }
        }
        with tempfile.TemporaryDirectory(dir=ROOT_DIR) as tmpdir:
            policy_path = Path(tmpdir) / "policy.json"
            policy_path.write_text(json.dumps(policy), encoding="utf-8")

            ok_proc = self._run_cli(
                "resolve",
                "--role",
                "gemini-strong",
                "--policy",
                str(policy_path),
                "--t3",
                str(T3_FIXTURE),
                "--json",
            )
            self.assertEqual(ok_proc.returncode, 0, ok_proc.stderr)
            ok_data = json.loads(ok_proc.stdout)
            self.assertTrue(ok_data["ok"])
            self.assertEqual(ok_data["model_id"], "gemini-4-neon")

            fail_proc = self._run_cli(
                "resolve",
                "--role",
                "gemini-strong",
                "--policy",
                str(policy_path),
                "--t3",
                str(T3_FIXTURE),
                "--override",
                "antigravity:gemini-4-neon:low",
                "--json",
            )
            self.assertEqual(fail_proc.returncode, 2)
            fail_data = json.loads(fail_proc.stdout)
            self.assertFalse(fail_data["ok"])
            self.assertEqual(fail_data["reason"], "forbidden_thinking")

            # Also verify failure without --json still prints JSON and exits 2
            fail_plain = self._run_cli(
                "resolve",
                "--role",
                "unknown-role",
                "--policy",
                str(policy_path),
                "--t3",
                str(T3_FIXTURE),
            )
            self.assertEqual(fail_plain.returncode, 2)
            fail_plain_data = json.loads(fail_plain.stdout)
            self.assertFalse(fail_plain_data["ok"])
            self.assertEqual(fail_plain_data["reason"], "unknown_role")


if __name__ == "__main__":
    unittest.main()
