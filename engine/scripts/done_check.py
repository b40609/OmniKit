# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""完工宣稱 Stop 閘：空殼（先跑紅燈用，實作在下一個 commit）。"""
import sys
from dataclasses import dataclass, field


@dataclass
class Result:
    triggered: bool = False
    problems: list = field(default_factory=list)
    hints: list = field(default_factory=list)


def check(message, cwd=None, session_start=None, done_paths=(), runner=None) -> Result:
    return Result()


def done_paths_this_turn(path) -> list:
    return []


def handle(data, env=None, runner=None):
    return None


def main() -> int:
    return 0


if __name__ == "__main__":
    sys.exit(1 if "--selftest" in sys.argv else main())
