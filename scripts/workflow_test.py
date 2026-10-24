from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from scripts import release


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/release-automation.yml"


class WorkflowPolicyTest(unittest.TestCase):
    def test_schedule_is_detection_only_and_manual_run_can_publish(self):
        workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        self.assertIn("schedule", workflow["on"])
        self.assertIn("workflow_dispatch", workflow["on"])

        detect_steps = workflow["jobs"]["detect"]["steps"]
        for name in ("Validate execution ref", "Plan and validate release"):
            step = next(step for step in detect_steps if step["name"] == name)
            expression = step["env"]["CHECK_ONLY"]
            self.assertRegex(expression, r"github\.event_name\s*==\s*'schedule'\s*\|\|\s*inputs\.check_only")

        release_condition = workflow["jobs"]["release"]["if"]
        self.assertRegex(
            release_condition,
            r"github\.event_name\s*==\s*'workflow_dispatch'\s*&&\s*"
            r"needs\.detect\.outputs\.should_release\s*==\s*'true'",
        )

        candidate = "1.4.2"
        scheduled_plan = release.make_plan(candidate, [], "1.4.1", "automation/released/v", True)
        manual_plan = release.make_plan(candidate, [], "1.4.1", "automation/released/v", False)
        self.assertFalse(scheduled_plan.should_release)
        self.assertTrue(manual_plan.should_release)


if __name__ == "__main__":
    unittest.main()
