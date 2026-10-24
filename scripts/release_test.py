from __future__ import annotations

import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from scripts import release


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class ReleaseTest(unittest.TestCase):
    def test_fetch_latest_version_uses_github_latest_and_token(self):
        opener = mock.Mock(return_value=Response(json.dumps({
            "tag_name": "v1.4.2", "draft": False, "prerelease": False
        }).encode()))
        self.assertEqual(
            release.fetch_latest_version(release.LATEST_RELEASE_API, "token", opener),
            "1.4.2",
        )
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, release.LATEST_RELEASE_API)
        self.assertEqual(request.get_header("Accept"), "application/vnd.github+json")
        self.assertEqual(request.get_header("Authorization"), "Bearer token")

    def test_fetch_latest_version_rejects_invalid_responses(self):
        valid = {"tag_name": "v1.4.2", "draft": False, "prerelease": False}
        cases = [
            (b"{broken", "lookup failed"),
            (b"[]", "must be an object"),
            (json.dumps({"tag_name": "v1.4.2", "prerelease": False}).encode(), "draft"),
            (json.dumps({"tag_name": "v1.4.2", "draft": False}).encode(), "prerelease"),
            (json.dumps({**valid, "draft": True}).encode(), "draft"),
            (json.dumps({**valid, "prerelease": True}).encode(), "prerelease"),
            (json.dumps({**valid, "draft": 0}).encode(), "draft"),
            (json.dumps({**valid, "tag_name": "1.4.2"}).encode(), "tag"),
            (json.dumps({**valid, "tag_name": "v1.4.2-rc1"}).encode(), "tag"),
            (json.dumps({**valid, "tag_name": 142}).encode(), "tag"),
        ]
        for payload, error in cases:
            with self.subTest(payload=payload), self.assertRaisesRegex(
                release.ReleaseError, error
            ):
                release.fetch_latest_version(
                    release.LATEST_RELEASE_API,
                    opener=mock.Mock(return_value=Response(payload)),
                )

    def test_fetch_latest_version_reports_http_error(self):
        error = urllib.error.HTTPError(release.LATEST_RELEASE_API, 403, "Forbidden", {}, None)
        with self.assertRaisesRegex(release.ReleaseError, "HTTP 403"):
            release.fetch_latest_version(
                release.LATEST_RELEASE_API, opener=mock.Mock(side_effect=error)
            )

    def test_plan_authenticates_only_the_upstream_latest_url(self):
        for url, expected_token in (
            (release.LATEST_RELEASE_API, "token"),
            ("https://example.invalid/releases/latest", ""),
        ):
            with self.subTest(url=url), mock.patch.dict(
                "os.environ", {"GH_TOKEN": "token"}
            ), mock.patch.object(
                release, "fetch_latest_version", return_value="1.4.2"
            ) as latest, mock.patch.object(
                release, "list_completed_versions", return_value=[]
            ), mock.patch.object(release, "fetch_release") as by_tag, mock.patch(
                "sys.stdout", new_callable=io.StringIO
            ):
                args = release.make_parser().parse_args([
                    "plan", "--version-url", url, "--baseline-version", "1.4.1",
                    "--tag-prefix", "automation/released/v",
                ])
                release.plan_command(args)
                latest.assert_called_once_with(url, expected_token)
                by_tag.assert_called_once_with("1.4.2", "token")

    def test_plan_requires_newer_unmarked_version(self):
        plan = release.make_plan(
            "1.4.2", ["1.4.1"], "1.4.1", "automation/released/v", False
        )
        self.assertTrue(plan.should_release)
        self.assertEqual(plan.marker_tag, "automation/released/v1.4.2")

    def test_plan_resumes_version_without_marker(self):
        plan = release.make_plan(
            "1.4.2", [], "1.4.1", "automation/released/v", False
        )
        self.assertTrue(plan.should_release)

    def test_plan_skips_completed_version(self):
        plan = release.make_plan(
            "1.4.2", ["1.4.2"], "1.4.1", "automation/released/v", False
        )
        self.assertFalse(plan.should_release)

    def test_plan_rejects_downgrade(self):
        with self.assertRaisesRegex(release.ReleaseError, "downgrade"):
            release.make_plan(
                "1.4.1", ["1.4.2"], "1.4.1", "automation/released/v", False
            )

    def test_update_recipe_changes_version_and_source_tag(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe = Path(directory) / "snapcraft.yaml"
            recipe.write_text(
                "name: juicefs\nversion: 1.4.1\nparts:\n"
                "  juicefs:\n    source-tag: v1.4.1\n",
                encoding="utf-8",
            )
            self.assertTrue(release.update_recipe(recipe, "1.4.2"))
            self.assertEqual(
                recipe.read_text(encoding="utf-8"),
                "name: juicefs\nversion: 1.4.2\nparts:\n"
                "  juicefs:\n    source-tag: v1.4.2\n",
            )
            self.assertFalse(release.update_recipe(recipe, "1.4.2"))

    def test_update_recipe_rejects_inconsistent_source_tag(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe = Path(directory) / "snapcraft.yaml"
            recipe.write_text(
                "version: 1.4.1\nparts:\n  juicefs:\n    source-tag: v1.4.0\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(release.ReleaseError, "disagree"):
                release.update_recipe(recipe, "1.4.2")


if __name__ == "__main__":
    unittest.main()
