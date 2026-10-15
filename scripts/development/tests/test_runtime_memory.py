"""Exercise startup commands without launching services or touching a live stack."""

import os
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "dev-stack.sh"
HARNESS = """
source "$1"
alive() { return 1; }
port_busy() { return 1; }
wait_http() { return 0; }
launch() { printf 'LAUNCH'; printf '\\t%s' "$@"; printf '\\n'; }
halt() { printf 'HALT %s\\n' "$1"; }
deps_backend() { :; }
migrate() { :; }
"$2" "${3:-be}"
"""


class RuntimeMemoryTests(unittest.TestCase):
    def run_command(self, command="start_be", **overrides):
        env = {k: v for k, v in os.environ.items() if not k.startswith("LABELX_")}
        env.update(overrides)
        return subprocess.run(  # noqa: S603 — fixed harness, no external command input
            ["/bin/bash", "-c", HARNESS, "runtime-test", str(SCRIPT), command],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def worker_args(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = [line.split("\t") for line in result.stdout.splitlines()]
        return next(line for line in lines if line[:2] == ["LAUNCH", "worker"])

    def test_defaults_bound_pool_and_recycle_workers(self):
        args = self.worker_args(self.run_command())
        self.assertEqual(args[args.index("--concurrency") + 1], "2")
        self.assertEqual(args[args.index("--max-tasks-per-child") + 1], "20")
        self.assertEqual(args[args.index("--max-memory-per-child") + 1], "393216")

    def test_operator_can_override_limits(self):
        args = self.worker_args(
            self.run_command(
                LABELX_WORKER_CONCURRENCY="1",
                LABELX_WORKER_MAX_TASKS_PER_CHILD="10",
                LABELX_WORKER_MAX_MEMORY_KIB="524288",
            )
        )
        self.assertEqual(args[args.index("--concurrency") + 1], "1")
        self.assertEqual(args[args.index("--max-tasks-per-child") + 1], "10")
        self.assertEqual(args[args.index("--max-memory-per-child") + 1], "524288")

    def test_autoreload_remains_on_by_default_and_can_be_disabled(self):
        self.assertNotIn("--noreload", self.run_command().stdout)
        result = self.run_command(LABELX_DJANGO_AUTORELOAD="0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--noreload", result.stdout)

    def test_bad_limits_fail_before_stopping_or_launching_any_service(self):
        for command in ("start_be", "cmd_restart", "cmd_refresh", "cmd_start"):
            for key in (
                "LABELX_WORKER_CONCURRENCY",
                "LABELX_WORKER_MAX_TASKS_PER_CHILD",
                "LABELX_WORKER_MAX_MEMORY_KIB",
            ):
                for value in ("", "0", "-1", "1.5", "two", "2;echo unsafe"):
                    with self.subTest(command=command, key=key, value=value):
                        result = self.run_command(command, **{key: value})
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn(key, result.stderr)
                        self.assertNotIn("HALT", result.stdout)
                        self.assertNotIn("LAUNCH", result.stdout)

    def test_bad_autoreload_value_fails_before_restart(self):
        result = self.run_command("cmd_restart", LABELX_DJANGO_AUTORELOAD="yes")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("HALT", result.stdout)

    def test_frontend_restart_is_independent_of_worker_settings(self):
        # The harness defaults to a backend restart; explicitly exercise the FE branch.
        env = {**os.environ, "LABELX_WORKER_CONCURRENCY": "bad"}
        result = subprocess.run(  # noqa: S603 — fixed harness, no external command input
            ["/bin/bash", "-c", HARNESS, "runtime-test", str(SCRIPT), "cmd_restart", "fe"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HALT fe", result.stdout)
        self.assertNotIn("HALT worker", result.stdout)


if __name__ == "__main__":
    unittest.main()
