"""Static checks on the container and deployment files.

These read the files as text and need no Docker. They catch the drift a build
would not: an environment variable spelled differently from the one the app
reads, a Poetry pin that no longer matches, the desktop UI leaking into the
image, or an entrypoint that takes ownership of the user's share.
"""

import re
import unittest
from pathlib import Path

import yaml

from src.web import config


REPO_ROOT = Path(__file__).resolve().parent.parent

DOCKERFILE = REPO_ROOT / "Dockerfile"
ENTRYPOINT = REPO_ROOT / "docker" / "entrypoint.sh"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"
LOCAL_COMPOSE = REPO_ROOT / "docker-compose.yml"
DEPLOY_COMPOSE = REPO_ROOT / "deploy" / "docker-compose.yml"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

POETRY_VERSION = "2.5.1"
POETRY_PIN = re.compile(r"poetry==([0-9][0-9A-Za-z.]*)")

ENV_NAME = re.compile(r"\bPAIRRANK_[A-Z0-9_]+\b")


def _config_env_names() -> set[str]:
    """Every ``PAIRRANK_*`` name src/web/config.py defines as a constant."""
    return {
        value
        for name, value in vars(config).items()
        if name.isupper() and isinstance(value, str) and value.startswith("PAIRRANK_")
    }


class TestTheDeployFiles(unittest.TestCase):
    """The container and compose files agree with the code they run."""

    def test_every_env_name_is_one_the_app_reads(self):
        known = _config_env_names()
        self.assertTrue(known)
        for path in (DOCKERFILE, ENTRYPOINT, LOCAL_COMPOSE, DEPLOY_COMPOSE):
            with self.subTest(path=path.relative_to(REPO_ROOT).as_posix()):
                used = set(ENV_NAME.findall(path.read_text(encoding="utf-8")))
                self.assertEqual(used - known, set())

    def test_the_dockerfile_pins_poetry(self):
        text = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn(f"poetry=={POETRY_VERSION}", text)

    def test_the_image_leaves_out_the_desktop_ui(self):
        lines = DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        self.assertIn("src/ui/", [line.strip() for line in lines])

    def test_the_entrypoint_never_chowns(self):
        # Commands only: the comment explaining why there is no chown names it.
        commands = [
            line
            for line in ENTRYPOINT.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        ]
        self.assertFalse([line for line in commands if "chown" in line])

    def test_the_entrypoint_has_unix_line_endings(self):
        # A CRLF shebang makes the kernel look for "/bin/sh\r" and the
        # container dies before printing anything.
        self.assertNotIn(b"\r", ENTRYPOINT.read_bytes())


class TestTheWorkflow(unittest.TestCase):
    """The CI workflow installs what the image does and publishes only when allowed."""

    @classmethod
    def setUpClass(cls):
        """Parse the workflow once."""
        cls.workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))

    def steps(self):
        """
        Every step of every job, with the job it belongs to.

        Returns:
            list[tuple[str, dict]]: (job name, step) pairs.
        """
        return [
            (job_name, step)
            for job_name, job in self.workflow["jobs"].items()
            for step in job.get("steps", [])
        ]

    def test_ci_pins_the_same_poetry_as_the_dockerfile(self):
        pins = {
            path.name: POETRY_PIN.findall(path.read_text(encoding="utf-8"))
            for path in (DOCKERFILE, WORKFLOW)
        }
        self.assertEqual(pins, {"Dockerfile": [POETRY_VERSION], "ci.yml": [POETRY_VERSION]})

    def test_every_publish_step_is_guarded(self):
        publishing = [
            (job_name, step)
            for job_name, step in self.steps()
            if "ghcr.io" in str(step.get("with", {}).get("registry", ""))
            or str(step.get("with", {}).get("push", "")).lower() == "true"
        ]
        # The login and the push, at least; a rename must not empty this.
        self.assertGreaterEqual(len(publishing), 2)
        for job_name, step in publishing:
            with self.subTest(job=job_name, step=step.get("name", step.get("uses"))):
                condition = step.get("if", "")
                self.assertIn("vars.PUBLISH_IMAGE == 'true'", condition)
                self.assertIn("github.ref == 'refs/heads/main'", condition)
                self.assertIn("github.event_name == 'push'", condition)
                self.assertNotIn("||", condition)


if __name__ == "__main__":
    unittest.main()
