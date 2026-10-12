"""R05: the hand-written contract and the runtime schema must not drift for M-03 operations.

Counts errors/warnings of schema generation (exit code 0 alone is not enough) and compares the
contract with the generated schema semantically. A view that spectacular silently ignores (for
example a plain function route) shows up as an operation missing from the runtime schema.
"""

import subprocess
import sys
from pathlib import Path

from tests.contract_parity import M03, compare, load, ops

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parents[1]
CONTRACT = ROOT / "docs" / "04-api" / "openapi.yaml"

# Known, explicitly accepted response-code differences. Every entry needs a reason; the test
# fails if an entry stops being true so the list cannot rot. Currently none.
ACCEPTED_CODE_DIFFS: dict[tuple[str, str], tuple[list[str], list[str]]] = {}


def _generate(tmp_path: Path) -> Path:
    """Run the same command CI runs; a warning or error makes it exit non-zero."""
    out = tmp_path / "runtime.yaml"
    completed = subprocess.run(  # noqa: S603 - fixed command, no user input
        [
            sys.executable,
            "manage.py",
            "spectacular",
            "--validate",
            "--fail-on-warn",
            "--file",
            str(out),
        ],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return out


def test_runtime_schema_generation_has_no_errors_or_warnings(tmp_path):
    # Exit code 0 under --fail-on-warn means zero warnings and zero errors.
    assert _generate(tmp_path).exists()


def test_m03_contract_matches_runtime_schema(tmp_path):
    runtime_path = _generate(tmp_path)
    result = compare(str(CONTRACT), str(runtime_path), "m03")

    # Scope guard: the filter must still see the M-03 surface (not silently shrink to nothing).
    in_scope = [
        key for key in ops(load(str(CONTRACT))) if key[1] in M03 or key[1].startswith(M03[:8])
    ]
    assert len(in_scope) >= 20, in_scope

    assert result["onlyDocs"] == [], "contract operations missing in runtime"
    assert result["onlyRuntime"] == [], "runtime operations missing in contract"
    assert result["opId"] == []
    assert result["params"] == []
    assert result["body"] == []
    assert result["shapes"] == [], "\n".join(map(str, result["shapes"]))

    seen = {}
    for entry in result["codes"]:
        key, _docs_label, docs_only, _rt_label, runtime_only = entry
        seen[key] = (docs_only, runtime_only)
    assert seen == ACCEPTED_CODE_DIFFS, seen
