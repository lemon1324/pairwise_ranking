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


PUBLISHING_COMMANDS = ("docker push", "imagetools create", "--push")

# Every condition that lets a job or step publish must hold all three.
PUBLISH_GUARDS = (
    "github.event_name == 'push'",
    "github.ref == 'refs/heads/main'",
    "vars.PUBLISH_IMAGE == 'true'",
)


def _dockerignore_regex(pattern: str) -> re.Pattern:
    """
    Compile one .dockerignore pattern the way Docker reads it.

    Covers the syntax the file uses: ``*`` within one path segment, ``**``
    across any number of them, and a trailing ``/``, which Docker cleans off.

    Args:
        pattern: The pattern, without any leading ``!``.

    Returns:
        re.Pattern: A regex matching a whole slash-separated path.
    """
    pattern = pattern.strip("/")
    parts = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            parts.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            parts.append(".*")
            i += 2
        elif pattern[i] == "*":
            parts.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(parts))


def _dockerignore_excludes(text: str, path: str) -> bool:
    """
    Whether a .dockerignore leaves a file out of the build context.

    Docker's rules: every pattern is tried in order and the last one to match
    decides, ``!`` re-including; a pattern matching a parent directory matches
    everything under it.

    Args:
        text: The .dockerignore contents.
        path: A slash-separated path relative to the context root.

    Returns:
        bool: True if the file is excluded.
    """
    segments = path.split("/")
    candidates = ["/".join(segments[:n]) for n in range(1, len(segments) + 1)]
    excluded = False
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        regex = _dockerignore_regex(line[1:] if negated else line)
        if any(regex.fullmatch(candidate) for candidate in candidates):
            excluded = not negated
    return excluded


def _is_publishing(step: dict) -> bool:
    """
    Whether a workflow step can write to a registry.

    A build step counts unless its ``push`` is literally false (an expression
    might be true), as does any registry login and any shell command that
    pushes. Read-only commands such as ``imagetools inspect`` do not.

    Args:
        step: One step of a job.

    Returns:
        bool: True if the step logs in to or pushes to a registry.
    """
    with_ = step.get("with", {}) or {}
    if "ghcr.io" in str(with_.get("registry", "")):
        return True
    if "push" in with_ and str(with_["push"]).strip().lower() != "false":
        return True
    if str(step.get("uses", "")).startswith("docker/login-action"):
        return True
    run = str(step.get("run", ""))
    return any(command in run for command in PUBLISHING_COMMANDS)


def _grants_write(permissions, scope: str) -> bool:
    """
    Whether a workflow or job ``permissions`` block grants write on a scope.

    Args:
        permissions: The block as parsed: a mapping, a string such as
            ``write-all``, or None when absent.
        scope: The permission scope, e.g. ``packages``.

    Returns:
        bool: True if the block lets the token write to that scope.
    """
    if isinstance(permissions, str):
        return permissions.strip() == "write-all"
    return isinstance(permissions, dict) and permissions.get(scope) == "write"


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

    def test_the_image_listens_on_every_interface(self):
        # The app binds loopback by default; inside a container that would be
        # unreachable through the published port.
        text = DOCKERFILE.read_text(encoding="utf-8")
        self.assertRegex(text, rf"\b{config.HOST_VAR}=0\.0\.0\.0\b")

    def test_the_local_stack_publishes_on_loopback_only(self):
        ports = yaml.safe_load(LOCAL_COMPOSE.read_text(encoding="utf-8"))[
            "services"
        ]["pairwise-ranking"]["ports"]
        self.assertTrue(ports)
        for port in ports:
            self.assertTrue(str(port).startswith("127.0.0.1:"), port)

    def test_the_image_leaves_out_the_desktop_ui(self):
        text = DOCKERIGNORE.read_text(encoding="utf-8")
        self.assertTrue((REPO_ROOT / "src" / "ui" / "main_window.py").is_file())
        self.assertTrue(_dockerignore_excludes(text, "src/ui/main_window.py"))

    def test_the_image_gets_what_the_web_app_runs(self):
        text = DOCKERIGNORE.read_text(encoding="utf-8")
        for path in ("src/web/app.py", "web_main.py", "docker/entrypoint.sh"):
            with self.subTest(path=path):
                self.assertTrue((REPO_ROOT / path).is_file())
                self.assertFalse(_dockerignore_excludes(text, path))

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

    def assert_publish_guarded(self, condition):
        """Fail unless an ``if`` condition holds every publish guard."""
        condition = str(condition or "")
        for guard in PUBLISH_GUARDS:
            self.assertIn(guard, condition)
        self.assertNotIn("||", condition)

    def jobs_granting(self, scope):
        """Names of the jobs whose own permissions grant write on ``scope``."""
        return {
            job_name
            for job_name, job in self.workflow["jobs"].items()
            if _grants_write(job.get("permissions"), scope)
        }

    def test_every_publish_step_is_guarded(self):
        publishing = [
            (job_name, step) for job_name, step in self.steps() if _is_publishing(step)
        ]
        # The login and the push, at least; a rename must not empty this.
        self.assertGreaterEqual(len(publishing), 2)
        for job_name, step in publishing:
            with self.subTest(job=job_name, step=step.get("name", step.get("uses"))):
                self.assert_publish_guarded(step.get("if"))

    def test_only_a_guarded_job_can_write_packages(self):
        # The build and smoke test run on every push and pull request; only a
        # job that cannot run otherwise may hold a registry-writing token.
        self.assertFalse(_grants_write(self.workflow.get("permissions"), "packages"))
        writers = self.jobs_granting("packages")
        self.assertTrue(writers)
        for job_name in writers:
            with self.subTest(job=job_name):
                job = self.workflow["jobs"][job_name]
                self.assert_publish_guarded(job.get("if"))
                # Publishes only what passed the smoke test.
                needs = job.get("needs", [])
                self.assertIn("image", [needs] if isinstance(needs, str) else needs)

    def test_every_publish_step_is_in_the_publishing_job(self):
        writers = self.jobs_granting("packages")
        for job_name, step in self.steps():
            if _is_publishing(step):
                with self.subTest(job=job_name, step=step.get("name", step.get("uses"))):
                    self.assertIn(job_name, writers)

    def test_only_the_badge_job_can_write_contents(self):
        self.assertFalse(_grants_write(self.workflow.get("permissions"), "contents"))
        self.assertEqual(self.jobs_granting("contents"), {"badge"})


if __name__ == "__main__":
    unittest.main()
