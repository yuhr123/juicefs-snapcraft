#!/usr/bin/env python3
"""Plan a release and update the Snapcraft recipe safely."""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any


VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
VERSION_LINE = re.compile(r"^version:\s*([^\s#]+)(?:\s+#.*)?$", re.MULTILINE)
SOURCE_TAG_LINE = re.compile(
    r"^(\s+)source-tag:\s*([^\s#]+)(?:\s+#.*)?$", re.MULTILINE
)
RELEASE_API = "https://api.github.com/repos/juicedata/juicefs/releases/tags/v{version}"


class ReleaseError(RuntimeError):
    """Raised when release state cannot be determined safely."""


@dataclasses.dataclass(frozen=True)
class ReleasePlan:
    version: str
    previous_version: str
    marker_tag: str
    is_new: bool
    should_release: bool
    reason: str


def validate_version(version: str) -> str:
    version = version.strip()
    if not VERSION_PATTERN.fullmatch(version):
        raise ReleaseError("version must be a stable semantic version such as 1.4.1")
    return version


def version_key(version: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in validate_version(version).split("."))


def fetch_text(
    url: str,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> str:
    request = urllib.request.Request(
        url, headers={"User-Agent": "juicefs-snap-release-automation"}
    )
    try:
        with opener(request, timeout=30) as response:
            raw = response.read(256)
    except urllib.error.HTTPError as exc:
        raise ReleaseError(f"version endpoint returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ReleaseError(f"version endpoint request failed: {exc}") from exc
    try:
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ReleaseError("version endpoint must return UTF-8 text") from exc


def fetch_release(
    version: str,
    token: str = "",
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    request = urllib.request.Request(
        RELEASE_API.format(version=version),
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "juicefs-snap-release-automation",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with opener(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise ReleaseError(f"GitHub release lookup failed with HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"GitHub release lookup failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReleaseError("GitHub release response must be an object")
    if payload.get("tag_name") != f"v{version}":
        raise ReleaseError(f"GitHub release tag does not match v{version}")
    if payload.get("draft") is not False:
        raise ReleaseError(f"v{version} is still a draft")
    if payload.get("prerelease") is not False:
        raise ReleaseError(f"v{version} is a prerelease")
    return payload


def list_completed_versions(
    remote: str,
    tag_prefix: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> list[str]:
    result = runner(
        ["git", "ls-remote", "--tags", remote, f"refs/tags/{tag_prefix}*"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ReleaseError(
            f"failed to list release marker tags: {result.stderr.strip()}"
        )
    versions: set[str] = set()
    ref_prefix = f"refs/tags/{tag_prefix}"
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 2:
            raise ReleaseError(f"unexpected git ls-remote output: {line!r}")
        ref = fields[1]
        if ref.endswith("^{}") or not ref.startswith(ref_prefix):
            continue
        version = ref.removeprefix(ref_prefix)
        validate_version(version)
        versions.add(version)
    return sorted(versions, key=version_key)


def make_plan(
    candidate: str,
    completed_versions: Sequence[str],
    baseline_version: str,
    tag_prefix: str,
    check_only: bool,
) -> ReleasePlan:
    candidate = validate_version(candidate)
    completed = {validate_version(version) for version in completed_versions}
    baseline = validate_version(baseline_version)
    previous = max(completed | {baseline}, key=version_key)
    if version_key(candidate) < version_key(previous):
        raise ReleaseError(
            f"refusing to downgrade from completed version {previous} to {candidate}"
        )
    marker = f"{tag_prefix}{candidate}"
    if candidate == baseline or candidate in completed:
        return ReleasePlan(
            candidate,
            previous,
            marker,
            False,
            False,
            f"version {candidate} is already marked complete",
        )
    return ReleasePlan(
        candidate,
        previous,
        marker,
        True,
        not check_only,
        (
            f"version {candidate} is newer than {previous}; check-only mode"
            if check_only
            else f"version {candidate} is newer than {previous}; release required"
        ),
    )


def write_outputs(path: str, values: dict[str, str | bool]) -> None:
    with Path(path).open("a", encoding="utf-8") as stream:
        for key, value in values.items():
            rendered = str(value).lower() if isinstance(value, bool) else value
            stream.write(f"{key}={rendered}\n")


def update_recipe(path: Path, version: str) -> bool:
    version = validate_version(version)
    text = path.read_text(encoding="utf-8")
    versions = VERSION_LINE.findall(text)
    source_tags = SOURCE_TAG_LINE.findall(text)
    if len(versions) != 1:
        raise ReleaseError(f"expected exactly one top-level version in {path}")
    if len(source_tags) != 1:
        raise ReleaseError(f"expected exactly one source-tag in {path}")
    current_version = validate_version(versions[0])
    current_tag = source_tags[0][1]
    if current_tag != f"v{current_version}":
        raise ReleaseError(
            f"recipe version {current_version} and source-tag {current_tag} disagree"
        )
    if version_key(version) < version_key(current_version):
        raise ReleaseError(
            f"refusing to downgrade recipe from {current_version} to {version}"
        )
    if version == current_version:
        return False
    text = VERSION_LINE.sub(f"version: {version}", text, count=1)
    text = SOURCE_TAG_LINE.sub(
        lambda match: f"{match.group(1)}source-tag: v{version}", text, count=1
    )
    path.write_text(text, encoding="utf-8")
    return True


def plan_command(args: argparse.Namespace) -> None:
    if args.version_override and not args.check_only:
        raise ReleaseError("version override is allowed only with --check-only")
    candidate = args.version_override or validate_version(fetch_text(args.version_url))
    plan = make_plan(
        candidate,
        list_completed_versions(args.remote, args.tag_prefix),
        args.baseline_version,
        args.tag_prefix,
        args.check_only,
    )
    fetch_release(plan.version, args.github_token)
    if args.output_file:
        write_outputs(
            args.output_file,
            {
                "version": plan.version,
                "previous_version": plan.previous_version,
                "marker_tag": plan.marker_tag,
                "is_new": plan.is_new,
                "should_release": plan.should_release,
                "reason": plan.reason,
            },
        )
    print(plan.reason)


def update_command(args: argparse.Namespace) -> None:
    changed = update_recipe(Path(args.recipe), args.version)
    if args.output_file:
        write_outputs(args.output_file, {"changed": changed})
    print("recipe updated" if changed else "recipe already uses requested version")


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="plan and validate a release")
    plan.add_argument("--version-url", required=True)
    plan.add_argument("--version-override", default="")
    plan.add_argument("--baseline-version", required=True)
    plan.add_argument("--tag-prefix", required=True)
    plan.add_argument("--remote", default="origin")
    plan.add_argument("--check-only", action="store_true")
    plan.add_argument("--github-token", default="")
    plan.add_argument("--output-file")
    plan.set_defaults(handler=plan_command)

    update = subparsers.add_parser("update-recipe", help="update snapcraft.yaml")
    update.add_argument("--recipe", required=True)
    update.add_argument("--version", required=True)
    update.add_argument("--output-file")
    update.set_defaults(handler=update_command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        args.handler(args)
    except ReleaseError as exc:
        print(f"release automation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
