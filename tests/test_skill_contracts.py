from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"


EXPECTED_SKILLS = [
    "scribe-core",
    "scribe-writing",
    "scribe-state-merge",
    "scribe-review",
    "scribe-handoff",
    "scribe-recovery",
    "scribe-workflow-planning",
    "scribe-workflow-debugging",
    "scribe-workflow-implementation",
    "scribe-workflow-verification",
    "scribe-workflow-research",
]


class SkillContractTests(unittest.TestCase):
    def test_scribe_skills_have_required_frontmatter(self):
        for name in EXPECTED_SKILLS:
            with self.subTest(name=name):
                path = SKILLS / name / "SKILL.md"
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\n"))
                match = re.match(r"---\n(.*?)\n---\n", text, re.S)
                self.assertIsNotNone(match)
                frontmatter = match.group(1)
                self.assertIn(f"name: {name}", frontmatter)
                self.assertRegex(frontmatter, r"description: Use when .+")

    def test_core_skill_forbids_raw_chain_of_thought_capture(self):
        text = (SKILLS / "scribe-core" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Do not capture raw chain-of-thought", text)
        self.assertIn("Capture reasoning signals", text)


if __name__ == "__main__":
    unittest.main()
