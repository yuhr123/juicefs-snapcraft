from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class PublishStableTest(unittest.TestCase):
    def run_with_fake_snapcraft(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "snapcraft"
            executable.write_text(
                "#!/usr/bin/env python3\n"
                "import os, pathlib, sys\n"
                "log = pathlib.Path(os.environ['SNAPCRAFT_CALL_LOG'])\n"
                "calls = log.read_text().splitlines() if log.exists() else []\n"
                "calls.append(' '.join(sys.argv[1:]))\n"
                "log.write_text('\\n'.join(calls) + '\\n')\n"
                "sys.exit(0)\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)
            log = root / "calls"
            environment = {
                **os.environ,
                "PATH": f"{root}{os.pathsep}{os.environ['PATH']}",
                "SNAPCRAFT_CALL_LOG": str(log),
            }
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.publish_stable",
                    "--amd64-revision",
                    "35",
                    "--arm64-revision",
                    "36",
                ],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            return result, log.read_text().splitlines()

    def test_releases_both_exact_revisions(self):
        result, calls = self.run_with_fake_snapcraft()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [
            "release juicefs 35 latest/stable",
            "release juicefs 36 latest/stable",
        ])

    def test_retries_one_revision_without_changing_the_other(self):
        # Avoid a real wait while preserving the CLI and fake executable path.
        from scripts import publish_stable
        sleeps = []
        calls = []

        def runner(command, *, check):
            calls.append(command)
            failed = command[3] == "35" and len(calls) == 1
            return subprocess.CompletedProcess(command, 1 if failed else 0)

        publish_stable.release_revisions([35, 36], runner, sleeps.append)
        self.assertEqual([call[3] for call in calls], ["35", "35", "36"])
        self.assertEqual(sleeps, [30])

    def test_stops_after_three_failures_without_releasing_next_revision(self):
        from scripts import publish_stable
        calls = []

        def runner(command, *, check):
            calls.append(command)
            return subprocess.CompletedProcess(command, 1)

        with self.assertRaisesRegex(RuntimeError, "revision 35"):
            publish_stable.release_revisions([35, 36], runner, lambda _: None)
        self.assertEqual([call[3] for call in calls], ["35", "35", "35"])


if __name__ == "__main__":
    unittest.main()
