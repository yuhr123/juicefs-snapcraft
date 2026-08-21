#!/usr/bin/env python3
"""Wait for an exact multi-architecture JuiceFS Snap Store build set."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any


STORE_URL = "https://api.snapcraft.io/v2/snaps/info/juicefs"


class StoreError(RuntimeError):
    """Raised when the expected Store state cannot be established."""


@dataclasses.dataclass(frozen=True)
class Revision:
    architecture: str
    version: str
    revision: int
    sha3_384: str


def fetch_store(
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    request = urllib.request.Request(
        STORE_URL,
        headers={
            "Snap-Device-Series": "16",
            "User-Agent": "juicefs-snap-release-automation",
        },
    )
    try:
        with opener(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise StoreError(f"Snap Store returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise StoreError(f"Snap Store request failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise StoreError("Snap Store response must be an object")
    return payload


def select_revisions(
    payload: dict[str, Any],
    version: str,
    risk: str,
    architectures: Sequence[str],
) -> dict[str, Revision]:
    selected: dict[str, Revision] = {}
    entries = payload.get("channel-map", [])
    if not isinstance(entries, list):
        raise StoreError("Snap Store response has no channel-map array")
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        channel = entry.get("channel")
        download = entry.get("download")
        if not isinstance(channel, dict) or not isinstance(download, dict):
            continue
        architecture = channel.get("architecture")
        if (
            channel.get("track") != "latest"
            or channel.get("risk") != risk
            or architecture not in architectures
            or entry.get("version") != version
        ):
            continue
        revision = entry.get("revision")
        sha3_384 = download.get("sha3-384")
        if not isinstance(revision, int) or not isinstance(sha3_384, str):
            continue
        selected[architecture] = Revision(
            architecture, version, revision, sha3_384
        )
    return selected


def parse_expected(values: Sequence[str]) -> dict[str, int]:
    expected: dict[str, int] = {}
    for value in values:
        try:
            architecture, revision = value.split("=", 1)
            expected[architecture] = int(revision)
        except (ValueError, TypeError) as exc:
            raise StoreError(
                f"expected revision must have ARCH=REVISION form: {value!r}"
            ) from exc
    return expected


def wait_for_revisions(
    version: str,
    risk: str,
    architectures: Sequence[str],
    expected: dict[str, int],
    timeout: int,
    interval: int,
    fetcher: Callable[[], dict[str, Any]] = fetch_store,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Revision]:
    if set(expected) - set(architectures):
        unknown = ", ".join(sorted(set(expected) - set(architectures)))
        raise StoreError(f"expected revisions include unrequested architectures: {unknown}")
    deadline = time.monotonic() + timeout
    last_selected: dict[str, Revision] = {}
    last_error = ""
    while True:
        try:
            last_selected = select_revisions(
                fetcher(), version, risk, architectures
            )
            last_error = ""
        except StoreError as exc:
            last_error = str(exc)
        if set(last_selected) == set(architectures) and all(
            architecture not in expected
            or revision.revision == expected[architecture]
            for architecture, revision in last_selected.items()
        ):
            return last_selected
        if time.monotonic() >= deadline:
            state = ", ".join(
                f"{arch}=r{revision.revision}"
                for arch, revision in sorted(last_selected.items())
            ) or (f"request error: {last_error}" if last_error else "none")
            raise StoreError(
                f"timed out waiting for juicefs {version} in latest/{risk}; found {state}"
            )
        sleeper(interval)


def write_outputs(path: str, revisions: dict[str, Revision]) -> None:
    with Path(path).open("a", encoding="utf-8") as stream:
        for architecture, revision in sorted(revisions.items()):
            stream.write(f"{architecture}_revision={revision.revision}\n")
            stream.write(f"{architecture}_sha3_384={revision.sha3_384}\n")


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--risk", choices=("edge", "stable"), required=True)
    parser.add_argument(
        "--architecture", action="append", default=[], dest="architectures"
    )
    parser.add_argument("--expected-revision", action="append", default=[])
    parser.add_argument("--timeout", type=int, default=7200)
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--output-file")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    architectures = args.architectures or ["amd64", "arm64"]
    try:
        revisions = wait_for_revisions(
            args.version,
            args.risk,
            architectures,
            parse_expected(args.expected_revision),
            args.timeout,
            args.interval,
        )
    except StoreError as exc:
        print(f"Snap Store verification failed: {exc}", file=sys.stderr)
        return 1
    for architecture, revision in sorted(revisions.items()):
        print(
            f"verified latest/{args.risk} {architecture}: "
            f"{revision.version} revision {revision.revision}"
        )
    if args.output_file:
        write_outputs(args.output_file, revisions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
