from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts import release


class ReleaseTest(unittest.TestCase):
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
