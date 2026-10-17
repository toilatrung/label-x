"""R05: runtime schema generation must be free of errors and warnings (exit 0 is not enough)."""

import io

from django.core.management import call_command


def test_spectacular_validate_has_no_errors_or_warnings(tmp_path):
    stderr = io.StringIO()
    call_command(
        "spectacular", "--validate", "--fail-on-warn", file=str(tmp_path / "s.yaml"), stderr=stderr
    )
    assert "Error" not in stderr.getvalue()
    assert "Warning" not in stderr.getvalue()
