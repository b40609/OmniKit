# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""拍板回寫 CLI 入口（委派至 engine/skills/omnikit-eval/scripts/record_decision.py）。

供 OmniKeep EvaluatorAdapter（OmniKitAdapter）以 `python scripts/record_decision.py` 直接呼叫。
"""
import importlib.util
import sys
from pathlib import Path

_EVAL_SCRIPTS = Path(__file__).resolve().parents[1] / "engine" / "skills" / "omnikit-eval" / "scripts"
if str(_EVAL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_EVAL_SCRIPTS))

_spec = importlib.util.spec_from_file_location("_omnikit_record_decision_impl", _EVAL_SCRIPTS / "record_decision.py")
_impl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_impl)

SCHEMA_VERSION = _impl.SCHEMA_VERSION
CLI_VERSION = _impl.CLI_VERSION
record_decision = _impl.record_decision
selftest = _impl.selftest
main = _impl.main

if __name__ == "__main__":
    sys.exit(main())
