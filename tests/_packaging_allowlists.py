"""Single source of truth for the wheel/sdist file boundary.

Two callers share it, so the boundary cannot drift between CI and release day:

* ``tests/test_packaging.py`` imports it — the every-commit guard, which builds
  the artifacts and asserts the reports below are empty.
* ``bin/publish`` executes it as a script
  (``python3 tests/_packaging_allowlists.py --wheel ... --sdist ...``) against
  the artifacts it is about to upload, and aborts the release on any violation.

Both check the *built artifact*, never the ``[tool.hatch.build.targets.*]``
config that produced it, so a hatchling default change or an auto-discovered
stray file is caught just as surely as a widened include glob.

Both directions are checked. An allow-list alone only catches an artifact that
ships too *much*; a narrowed `packages` entry that drops the package would sail
through it, so each artifact also has a required-file list.

The leading underscore marks this as a private helper rather than a test module.
"""

from __future__ import annotations

import argparse
import re
import sys
import tarfile
import zipfile
from pathlib import Path

# The wheel is what pip installs: the SDK package and the wheel metadata.
WHEEL_ALLOWED_RE = re.compile(r"^(abmeter/|abmeter-[^/]+\.dist-info/)")

# A spot-check that the package actually made it in. Narrowing
# [tool.hatch.build.targets.wheel] packages to a subdirectory produces a wheel
# that is empty of violations but broken on import; the allow-list alone is blind
# to it. Three entries, one per level of the package tree, are enough to notice.
WHEEL_REQUIRED = ("abmeter/__init__.py", "abmeter/version.py", "abmeter/core/__init__.py")

# The sdist additionally carries the unit tests, plus the files hatchling forces
# into every source distribution (pyproject.toml, PKG-INFO, the VCS ignore file).
SDIST_ALLOWED_RE = re.compile(
    r"^(src/abmeter/|tests/|README\.md$|LICENSE\.txt$|pyproject\.toml$|PKG-INFO$|\.gitignore$)"
)

# Redundant with the allow-list by construction, and deliberately so: naming the
# monorepo-only paths gives a specific, actionable error for the exact regressions
# this guard exists to catch. `canonical_app/` and `emulator/` no longer live here
# (the recovery harness moved to the top-level canonical-apps/), so these entries
# only ever fire if someone reintroduces them.
SDIST_FORBIDDEN_RE = re.compile(r"^(mise\.toml$|CLAUDE\.md$|canonical_app/|emulator/|bin/)")

# Hatchling adds all four implicitly. Asserting their presence turns a silently
# metadata-less sdist into a loud failure.
SDIST_REQUIRED = ("README.md", "LICENSE.txt", "pyproject.toml", "PKG-INFO")

_SDIST_PREFIX_RE = re.compile(r"^abmeter-[^/]+/")


def wheel_files(wheel: Path) -> list[str]:
    """Every file in the wheel, as recorded in the zip (directories dropped)."""
    with zipfile.ZipFile(wheel) as archive:
        return [name for name in archive.namelist() if not name.endswith("/")]


def sdist_files(sdist: Path) -> list[str]:
    """Every non-directory entry in the sdist, ``abmeter-<version>/`` prefix stripped.

    Filtering on ``isdir()`` rather than ``isfile()`` is deliberate: ``isfile()``
    means "regular file", so a symlinked CLAUDE.md would slip past every check.
    A guard has to fail closed.
    """
    with tarfile.open(sdist, "r:gz") as archive:
        return [
            _SDIST_PREFIX_RE.sub("", member.name)
            for member in archive.getmembers()
            if not member.isdir()
        ]


def wheel_violations(wheel: Path) -> dict[str, list[str]]:
    """Report for the wheel. Empty lists mean the boundary holds."""
    files = wheel_files(wheel)
    present = set(files)
    return {
        "disallowed": [f for f in files if not WHEEL_ALLOWED_RE.match(f)],
        "missing": [f for f in WHEEL_REQUIRED if f not in present],
    }


def sdist_violations(sdist: Path) -> dict[str, list[str]]:
    """Report for the sdist. Empty lists mean the boundary holds."""
    files = sdist_files(sdist)
    present = set(files)
    return {
        "disallowed": [f for f in files if not SDIST_ALLOWED_RE.match(f)],
        "forbidden": [f for f in files if SDIST_FORBIDDEN_RE.match(f)],
        "missing": [f for f in SDIST_REQUIRED if f not in present],
    }


def _print_violations(header: str, files: list[str], hint: str) -> None:
    print(f"ERROR: {header}", file=sys.stderr)
    for name in files:
        print(f"  - {name}", file=sys.stderr)
    print(hint, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check built artifacts against the boundary.")
    parser.add_argument("--wheel", type=Path, required=True, help="path to the built .whl")
    parser.add_argument("--sdist", type=Path, required=True, help="path to the built .tar.gz")
    args = parser.parse_args(argv)

    wheel_hint = "Fix [tool.hatch.build.targets.wheel] in pyproject.toml."
    sdist_hint = "Fix [tool.hatch.build.targets.sdist] include= in pyproject.toml."
    ok = True

    wheel = wheel_violations(args.wheel)
    if wheel["disallowed"]:
        _print_violations(
            "wheel would ship files outside abmeter/** and *.dist-info/**:",
            wheel["disallowed"],
            wheel_hint,
        )
        ok = False
    if wheel["missing"]:
        _print_violations("wheel is missing required files:", wheel["missing"], wheel_hint)
        ok = False

    sdist = sdist_violations(args.sdist)
    if sdist["disallowed"]:
        _print_violations(
            "sdist would ship files outside the allowed set:", sdist["disallowed"], sdist_hint
        )
        ok = False
    if sdist["forbidden"]:
        _print_violations(
            "sdist would ship monorepo-only paths:", sdist["forbidden"], sdist_hint
        )
        ok = False
    if sdist["missing"]:
        _print_violations(
            "sdist is missing required files:", sdist["missing"], sdist_hint
        )
        ok = False

    if not ok:
        print("Aborting before upload.", file=sys.stderr)
        return 1

    print("OK - wheel and sdist contain only allowed files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
