"""Wheel/sdist content guard, the Python mirror of abmeter-sdk/spec/packaging_spec.rb.

Builds both artifacts with `uv build` into a temp directory and checks their file
lists against tests/_packaging_allowlists.py, the same module bin/publish runs
against the artifacts it is about to upload. A widened
[tool.hatch.build.targets.*] glob therefore fails in PR CI rather than on
release day, when the only remaining guard is a human reading a diff.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests._packaging_allowlists import sdist_violations, wheel_violations

SDK_ROOT = Path(__file__).resolve().parents[1]

# tests/ ships inside the sdist, so this module also runs for anyone building the
# package from source. They have no reason to have uv, and no network for the
# build env. Skipping there costs nothing: every context that gates a release
# (CI, mise run test, bin/publish's run inside the mirror) invokes pytest through
# uv, so uv is present by construction and the guard cannot silently vanish.
pytestmark = pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not on PATH")


def _one(out_dir: Path, pattern: str) -> Path:
    match = next(out_dir.glob(pattern), None)
    if match is None:
        built = sorted(path.name for path in out_dir.iterdir())
        pytest.fail(f"uv build produced no {pattern}; it built {built}")
    return match


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory):
    """Build the sdist and wheel once for the whole module."""
    out_dir = tmp_path_factory.mktemp("dist")
    subprocess.run(["uv", "build", "--out-dir", str(out_dir)], cwd=SDK_ROOT, check=True)
    return {
        "wheel": _one(out_dir, "abmeter-*-py3-none-any.whl"),
        "sdist": _one(out_dir, "abmeter-*.tar.gz"),
    }


@pytest.fixture(scope="module")
def wheel_report(artifacts):
    return wheel_violations(artifacts["wheel"])


@pytest.fixture(scope="module")
def sdist_report(artifacts):
    return sdist_violations(artifacts["sdist"])


def test_wheel_ships_only_the_sdk_package(wheel_report):
    assert wheel_report["disallowed"] == []


def test_wheel_contains_the_package(wheel_report):
    assert wheel_report["missing"] == []


def test_sdist_ships_only_allowed_files(sdist_report):
    assert sdist_report["disallowed"] == []


def test_sdist_excludes_monorepo_only_paths(sdist_report):
    assert sdist_report["forbidden"] == []


def test_sdist_contains_required_files(sdist_report):
    assert sdist_report["missing"] == []
