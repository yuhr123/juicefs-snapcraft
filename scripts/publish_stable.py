#!/usr/bin/env python3
"""Release the already verified Snap revisions to latest/stable."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Callable, Sequence


def positive_revision(value: str) -> int:
    try:
        revision = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("revision must be a positive integer") from exc
    if revision <= 0:
        raise argparse.ArgumentTypeError("revision must be a positive integer")
    return revision


def release_revisions(
    revisions: Sequence[int],
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    for revision in revisions:
        command = ["snapcraft", "release", "juicefs", str(revision), "latest/stable"]
        for attempt in range(1, 4):
            result = runner(command, check=False)
            if result.returncode == 0:
                break
            if attempt == 3:
                raise RuntimeError(f"failed to release revision {revision} after 3 attempts")
            print(
                f"revision {revision} release attempt {attempt} failed; retrying",
                file=sys.stderr,
                flush=True,
            )
            sleeper(30)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amd64-revision", required=True, type=positive_revision)
    parser.add_argument("--arm64-revision", required=True, type=positive_revision)
    args = parser.parse_args(argv)
    if args.amd64_revision == args.arm64_revision:
        parser.error("amd64 and arm64 revisions must differ")
    try:
        release_revisions([args.amd64_revision, args.arm64_revision])
    except (OSError, RuntimeError) as exc:
        print(f"stable release failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
