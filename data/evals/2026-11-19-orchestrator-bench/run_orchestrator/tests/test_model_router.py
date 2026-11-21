"""Unit tests for model_router package and CLI."""

from __future__ import annotations

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

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = WORKSPACE_ROOT / "fixtures"
T3_FIXTURE = FIXTURES_DIR / "t3_caps.json"
AGY_FIXTURE = FIXTURES_DIR / "agy_models.txt"


def _load_t3_fixture() -> dict:
    return json.loads(T3_FIXTURE.read_text(encoding="utf-8"))


class TestPackageExports(unittest.TestCase):
    def test_top_level_exports(self) -> None:
        self.assertIs(model_router.parse_t3_capabilities, parse_t3_capabilities)
        self.assertIs(model_router.parse_agy_models, parse_agy_models)
        self.assertIs(model_router.diff_catalogs, diff_catalogs)
        self.assertIs(model_router.resolve_role, resolve_role)


class TestCatalog(unittest.TestCase):
    def test_parse_t3_capabilities_fixture(self) -> None:
        items = parse_t3_capabilities(_load_t3_fixture())
        self.assertEqual(len(items), 8)

        by_key = {(item["provider_id"], item["model_id"]): item for item in items}

        grok = by_key[("grok", "grok-build")]
        self.assertEqual(grok["source"], "t3")
        self.assertEqual(grok["driver"], "grok")
        self.assertFalse(grok["enabled"])
        self.assertEqual(grok["label"], "Grok Build")
        self.assertIsNone(grok["thinking_param"])
        self.assertEqual(grok["thinking_values"], [])
        self.assertIsNone(grok["default_thinking"])

        opus = by_key[("claudeAgent", "claude-opus-5-5")]
        self.assertTrue(opus["enabled"])
        self.assertEqual(opus["thinking_param"], "effort")
        self.assertEqual(
            opus["thinking_values"],
            ["low", "medium", "high", "xhigh", "max", "ultrathink"],
        )
        self.assertEqual(opus["default_thinking"], "medium")

        neon = by_key[("antigravity", "gemini-4-neon")]
        self.assertTrue(neon["enabled"])
        self.assertEqual(neon["thinking_param"], "thinking_level")
        self.assertEqual(neon["thinking_values"], ["low", "medium", "high", "xhigh"])
        self.assertEqual(neon["default_thinking"], "high")

    def test_parse_t3_disabled_constraint_case_insensitive_and_label_fallback(self) -> None:
        data = {
            "providers": [
                {
                    "providerInstanceId": "custom_disabled",
                    "driverKind": "custom",
                    "canRunChildTask": True,
                    "constraints": ["Temporarily DISABLED for maintenance"],
                    "models": [{"id": "m-alpha"}],
                }
            ]
        }
        items = parse_t3_capabilities(data)
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0]["enabled"])
        self.assertEqual(items[0]["label"], "m-alpha")
        self.assertIsNone(items[0]["thinking_param"])

    def test_parse_agy_models_fixture_and_suffixes(self) -> None:
        items = parse_agy_models(AGY_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(len(items), 8)

        by_id = {item["model_id"]: item for item in items}
        self.assertEqual(by_id["gemini-4-neon-high"]["base_model"], "gemini-4-neon")
        self.assertEqual(by_id["gemini-4-neon-high"]["thinking_suffix"], "high")
        self.assertEqual(by_id["gemini-4-neon-xhigh"]["base_model"], "gemini-4-neon")
        self.assertEqual(by_id["gemini-4-neon-xhigh"]["thinking_suffix"], "xhigh")
        self.assertEqual(by_id["claude-opus-5-5-medium"]["base_model"], "claude-opus-5-5")
        self.assertEqual(by_id["claude-opus-5-5-medium"]["thinking_suffix"], "medium")
        self.assertEqual(
            by_id["gemini-pro-orchestrator-neon"]["base_model"],
            "gemini-pro-orchestrator-neon",
        )
        self.assertIsNone(by_id["gemini-pro-orchestrator-neon"]["thinking_suffix"])

    def test_parse_agy_models_low_max_and_blank_lines(self) -> None:
        text = (
            "\n"
            "Header without tab\n"
            "model-a-low\tModel A Low\r\n"
            "model-b-max\tModel B Max\n"
            "\tMissing Id\n"
        )
        items = parse_agy_models(text)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["base_model"], "model-a")
        self.assertEqual(items[0]["thinking_suffix"], "low")
        self.assertEqual(items[1]["base_model"], "model-b")
        self.assertEqual(items[1]["thinking_suffix"], "max")

    def test_diff_catalogs_added_removed_changed_and_source_fallback(self) -> None:
        old_items = [
            {
                "source": "t3",
                "provider_id": "p1",
                "model_id": "m-removed",
                "enabled": True,
                "thinking_values": ["low"],
                "default_thinking": "low",
            },
            {
                "source": "t3",
                "provider_id": "p1",
                "model_id": "m-changed",
                "enabled": True,
                "thinking_values": ["low", "medium"],
                "default_thinking": "medium",
            },
            {
                "source": "agy",
                "model_id": "agy-only-old",
                "enabled": True,
                "thinking_values": [],
                "default_thinking": None,
            },
        ]
        new_items = [
            {
                "source": "t3",
                "provider_id": "p1",
                "model_id": "m-changed",
                "enabled": False,
                "thinking_values": ["low", "medium", "high"],
                "default_thinking": "high",
            },
            {
                "source": "t3",
                "provider_id": "p2",
                "model_id": "m-added-2",
                "enabled": True,
                "thinking_values": [],
                "default_thinking": None,
            },
            {
                "source": "t3",
                "provider_id": "p1",
                "model_id": "m-added-1",
                "enabled": True,
                "thinking_values": [],
                "default_thinking": None,
            },
        ]
        diff = diff_catalogs(old_items, new_items)
        self.assertEqual(
            [(x["provider_id"], x["model_id"]) for x in diff["added"]],
            [("p1", "m-added-1"), ("p2", "m-added-2")],
        )
        self.assertEqual(
            [(x.get("provider_id") or x["source"], x["model_id"]) for x in diff["removed"]],
            [("agy", "agy-only-old"), ("p1", "m-removed")],
        )
        self.assertEqual(len(diff["changed"]), 1)
        chg = diff["changed"][0]
        self.assertEqual(chg["key"], ["p1", "m-changed"])
        self.assertEqual(
            chg["changes"],
            ["enabled", "thinking_values", "default_thinking"],
        )


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
                "fallback-role": {
                    "forbid_thinking": ["low", "medium"],
                    "candidates": [
                        {
                            "provider_id": "antigravity",
                            "model_pattern": "gemini-4-*",
                            "thinking": "low",
                        },
                        {
                            "provider_id": "antigravity",
                            "model_pattern": "gemini-4-argon",
                            "thinking": "xhigh",
                        },
                        {
                            "provider_id": "antigravity_ava",
                            "model_pattern": "gemini-3.8-*",
                            "thinking": "high",
                        },
                    ],
                },
                "lex-role": {
                    "forbid_thinking": [],
                    "candidates": [
                        {
                            "provider_id": "antigravity",
                            "model_pattern": "gemini-4-*",
                            "thinking": "high",
                        }
                    ],
                },
            }
        }

    def test_unknown_role(self) -> None:
        res = resolve_role("nonexistent", self.policy, self.catalog)
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "unknown_role")

    def test_policy_match_prefer_order_and_exclude(self) -> None:
        res = resolve_role("gemini-strong", self.policy, self.catalog)
        self.assertEqual(
            res,
            {
                "ok": True,
                "provider_id": "antigravity",
                "model_id": "gemini-4-neon",
                "thinking": "high",
                "thinking_param": "thinking_level",
                "matched_by": "policy",
                "fallback_index": 0,
            },
        )

    def test_policy_lexicographical_order_without_prefer_order(self) -> None:
        res = resolve_role("lex-role", self.policy, self.catalog)
        self.assertTrue(res["ok"])
        self.assertEqual(res["model_id"], "gemini-4-argon")

    def test_policy_fallback_on_forbidden_and_unsupported_thinking(self) -> None:
        res = resolve_role("fallback-role", self.policy, self.catalog)
        self.assertTrue(res["ok"])
        self.assertEqual(res["provider_id"], "antigravity_ava")
        self.assertEqual(res["model_id"], "gemini-3.8-flash")
        self.assertEqual(res["thinking"], "high")
        self.assertEqual(res["matched_by"], "policy")
        self.assertEqual(res["fallback_index"], 2)

    def test_no_candidate_available_reports_tried(self) -> None:
        policy = {
            "roles": {
                "empty-role": {
                    "forbid_thinking": ["low"],
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
                    ],
                }
            }
        }
        res = resolve_role("empty-role", policy, self.catalog)
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "no_candidate_available")
        self.assertEqual(len(res["tried"]), 2)
        self.assertEqual(res["tried"][0]["reason"], "forbidden_thinking")
        self.assertEqual(res["tried"][1]["reason"], "no_matching_model")

    def test_override_success(self) -> None:
        overrides = {
            "gemini-strong": {
                "provider_id": "claudeAgent",
                "model_id": "claude-opus-5-5",
                "thinking": "xhigh",
            }
        }
        res = resolve_role("gemini-strong", self.policy, self.catalog, overrides=overrides)
        self.assertEqual(
            res,
            {
                "ok": True,
                "provider_id": "claudeAgent",
                "model_id": "claude-opus-5-5",
                "thinking": "xhigh",
                "thinking_param": "effort",
                "matched_by": "override",
                "fallback_index": -1,
            },
        )

    def test_override_forbidden_thinking_fails_without_fallback(self) -> None:
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

    def test_override_unavailable_for_disabled_or_missing(self) -> None:
        disabled_ov = {
            "gemini-strong": {
                "provider_id": "grok",
                "model_id": "grok-build",
                "thinking": "high",
            }
        }
        res1 = resolve_role("gemini-strong", self.policy, self.catalog, overrides=disabled_ov)
        self.assertFalse(res1["ok"])
        self.assertEqual(res1["reason"], "override_unavailable")

        missing_ov = {
            "gemini-strong": {
                "provider_id": "antigravity",
                "model_id": "gemini-99-unknown",
                "thinking": "high",
            }
        }
        res2 = resolve_role("gemini-strong", self.policy, self.catalog, overrides=missing_ov)
        self.assertFalse(res2["ok"])
        self.assertEqual(res2["reason"], "override_unavailable")

    def test_override_unsupported_thinking(self) -> None:
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


class TestCLI(unittest.TestCase):
    def _run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "model_router.cli", *args],
            cwd=str(WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def test_cli_catalog_with_t3_and_agy(self) -> None:
        proc = self._run_cli(
            "catalog",
            "--t3",
            str(T3_FIXTURE),
            "--agy",
            str(AGY_FIXTURE),
            "--json",
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(len(payload), 16)
        self.assertEqual(sum(1 for x in payload if x["source"] == "t3"), 8)
        self.assertEqual(sum(1 for x in payload if x["source"] == "agy"), 8)

    def test_cli_diff_command(self) -> None:
        new_data = _load_t3_fixture()
        # Disable grok? Already disabled; toggle antigravity_ava and add a model
        new_data["providers"][-1]["canRunChildTask"] = False
        new_data["providers"][-1]["models"].append({"id": "gemini-3.8-pro", "label": "Gemini 3.8 Pro"})

        with tempfile.TemporaryDirectory(dir=WORKSPACE_ROOT) as tmpdir:
            new_path = Path(tmpdir) / "new_t3.json"
            new_path.write_text(json.dumps(new_data), encoding="utf-8")

            proc = self._run_cli(
                "diff",
                "--old",
                str(T3_FIXTURE),
                "--new",
                str(new_path),
                "--json",
            )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        diff = json.loads(proc.stdout)
        self.assertEqual(len(diff["added"]), 1)
        self.assertEqual(diff["added"][0]["model_id"], "gemini-3.8-pro")
        self.assertEqual(len(diff["changed"]), 1)
        self.assertEqual(diff["changed"][0]["changes"], ["enabled"])

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
        with tempfile.TemporaryDirectory(dir=WORKSPACE_ROOT) as tmpdir:
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
            self.assertEqual(ok_proc.returncode, 0, msg=ok_proc.stderr)
            ok_data = json.loads(ok_proc.stdout)
            self.assertTrue(ok_data["ok"])
            self.assertEqual(ok_data["model_id"], "gemini-4-neon")

            ov_ok_proc = self._run_cli(
                "resolve",
                "--role",
                "gemini-strong",
                "--policy",
                str(policy_path),
                "--t3",
                str(T3_FIXTURE),
                "--override",
                "antigravity:gemini-4-hydrogen:xhigh",
                "--json",
            )
            self.assertEqual(ov_ok_proc.returncode, 0, msg=ov_ok_proc.stderr)
            ov_ok_data = json.loads(ov_ok_proc.stdout)
            self.assertEqual(ov_ok_data["matched_by"], "override")
            self.assertEqual(ov_ok_data["model_id"], "gemini-4-hydrogen")
            self.assertEqual(ov_ok_data["thinking"], "xhigh")

            # Failure should exit with 2 and still print valid JSON even without --json
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
            )
            self.assertEqual(fail_proc.returncode, 2)
            fail_data = json.loads(fail_proc.stdout)
            self.assertFalse(fail_data["ok"])
            self.assertEqual(fail_data["reason"], "forbidden_thinking")

            unknown_proc = self._run_cli(
                "resolve",
                "--role",
                "missing-role",
                "--policy",
                str(policy_path),
                "--t3",
                str(T3_FIXTURE),
                "--json",
            )
            self.assertEqual(unknown_proc.returncode, 2)
            unknown_data = json.loads(unknown_proc.stdout)
            self.assertFalse(unknown_data["ok"])
            self.assertEqual(unknown_data["reason"], "unknown_role")


if __name__ == "__main__":
    unittest.main()
