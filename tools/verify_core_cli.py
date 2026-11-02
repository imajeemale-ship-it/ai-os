"""Verify the installed core CLI using disposable state, outside the checkout."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    executable = shutil.which("ai-os")
    if not executable:
        raise SystemExit("Install the package first: python -m pip install --no-deps .")
    with tempfile.TemporaryDirectory(prefix="ai-os-cli-") as directory:
        env = dict(os.environ)
        env["AI_OS_DB"] = str(Path(directory) / "verification.db")
        env.pop("PYTHONPATH", None)

        def run(*args, expected=0):
            result = subprocess.run([executable, *args], cwd=directory, env=env,
                                    capture_output=True, text=True, timeout=30)
            if result.returncode != expected:
                raise AssertionError(f"CLI {args[0]}: expected {expected}, got {result.returncode}")
            return json.loads(result.stdout) if result.stdout.strip() else None

        run("init")
        project = run("project", "add", "Portfolio verification")
        first = run("task", "add", project["id"], "Review first", "--priority", "1")
        second = run("task", "add", project["id"], "Review later", "--priority", "4")
        plan = run("plan")
        check(plan["recommended_next_action"]["task_id"] == first["id"], "Planner selected the wrong task")
        before = run("tasks")
        check(all(task["status"] == "ready" for task in before), "New tasks must be ready")
        dry = run("run")
        check(dry["accepted"] is False, "Dry run accepted a task")
        check(run("tasks") == before, "Dry run mutated tasks")
        run("run", "--accept-task", second["id"], expected=2)
        check(run("tasks") == before, "Rejected acceptance mutated tasks")
        accepted = run("run", "--accept-task", first["id"])
        check(accepted["accepted"] is True, "Explicit acceptance failed")
        states = {task["id"]: task["status"] for task in run("tasks")}
        check(states[first["id"]] == "in_progress", "Accepted task was not started")
        check(states[second["id"]] == "ready", "Other task state changed")
    print("PASS: installed CLI lifecycle, dry-run immutability, rejection, explicit acceptance")


if __name__ == "__main__":
    main()
