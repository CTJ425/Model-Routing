"""A throwaway project on tmp_path, shaped like a repo that ran /route:init."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "route", "hooks"))

BASE_CONFIG = {
    "version": 2,
    "paths": {"prod": ["src/"], "docs": "docs/agent", "specs": "docs/agent/specs"},
    "models": {"scout": "haiku", "builder": "sonnet",
               "reviewer": "sonnet", "scribe": "haiku"},
}


@pytest.fixture
def project(tmp_path):
    """-> Path to a fake project root with a config the guard can read."""
    for d in ("src", "tests", "docs/agent/specs", ".claude"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "a.ts").write_text("export const a = 1;\n")
    (tmp_path / "docs" / "agent" / "TASK.md").write_text("# Tasks\n")
    write_config(tmp_path, BASE_CONFIG)
    return tmp_path


def write_config(project, cfg: dict) -> None:
    path = os.path.join(str(project), ".claude", "route.config.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh)
