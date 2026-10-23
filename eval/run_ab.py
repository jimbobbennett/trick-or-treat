"""A/B test the trick-or-treat mod: the same tasks with the mod on and off.

Every session is traced by coding-harness-tracing (the Claude Code plugin),
loaded with --plugin-dir, into one Arize project. Each session sets
ARIZE_USER_ID to ghost-on or ghost-off, which lands on every trace as user.id,
so the two arms can be told apart in Arize. User-level settings are skipped (--setting-sources
project) so personal hooks don't add turns or noise.

Each run gets a fresh copy of haunted-house/, runs the task, then a checker
command decides whether the task was done.

Usage:
  python run_ab.py                     # all tasks, both arms, 1 repeat
  python run_ab.py --tasks t04 --repeats 2 -j 4
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE / "haunted-house"
MOD = HERE.parent  # the mod lives at the repo root
# coding-harness-tracing's Claude Code plugin. Install it first (see README).
TRACER = Path(os.environ.get(
    "TRACER_PLUGIN_DIR",
    Path.home() / ".claude/plugins/cache/coding-harness-tracing/claude-code-tracing/1.0.1",
))
RUNS_DIR = Path("/tmp/ab-runs")
RESULTS = HERE / "results.jsonl"
GHOST_LOGS = Path.home() / ".claude/trick-or-treat/logs"
PROJECT = "trick-or-treat-ab"


def dotenv() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k.startswith("ARIZE_")}
    dotfile = HERE.parent / ".env"
    if not dotfile.exists():
        return env
    for line in dotfile.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def settings_for(variant: str, task_id: str, run_id: str) -> Path:
    creds = dotenv()
    settings = {
        "env": {
            "ARIZE_API_KEY": creds["ARIZE_API_KEY"],
            "ARIZE_SPACE_ID": creds["ARIZE_SPACE_ID"],
            "ARIZE_PROJECT_NAME": PROJECT,
            "ARIZE_TRACE_ENABLED": "true",
            "ARIZE_LOG_PROMPTS": "true",
            "ARIZE_LOG_TOOL_DETAILS": "true",
            "ARIZE_LOG_TOOL_CONTENT": "true",
            "ARIZE_USER_ID": f"ghost-{variant}",
            "OTEL_RESOURCE_ATTRIBUTES": f"ab.variant={variant},ab.task={task_id},ab.run={run_id}",
        }
    }
    path = RUNS_DIR / f"{run_id}.settings.json"
    path.write_text(json.dumps(settings))
    return path


def run_one(task: dict, variant: str, repeat: int, model: str) -> dict:
    run_id = f"{task['id']}-{variant}-r{repeat}"
    work = RUNS_DIR / run_id
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(REPO, work)
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    # The haunted house needs git history for the commit and undo tasks.
    git = ["git", "-c", "user.name=ghost", "-c", "user.email=ghost@example.com"]
    subprocess.run(["git", "init", "-q"], cwd=work, check=True)
    subprocess.run([*git, "add", "-A"], cwd=work, check=True)
    subprocess.run([*git, "commit", "-qm", "haunted house"], cwd=work, check=True)
    if task.get("setup"):
        subprocess.run(task["setup"], shell=True, cwd=work, env=env, check=True)

    cmd = [
        "claude", "-p", task["prompt"],
        "--model", model,
        "--output-format", "json",
        "--setting-sources", "project",
        "--settings", str(settings_for(variant, task["id"], run_id)),
        "--allowedTools", "Bash", "Read", "Edit", "Write", "Glob", "Grep",
        "--plugin-dir", str(TRACER),
    ]
    if variant == "on":
        cmd += ["--plugin-dir", str(MOD)]

    started = time.time()
    proc = subprocess.run([shutil.which("claude") or "claude", *cmd[1:]], cwd=work, env=env, capture_output=True, text=True, timeout=600)
    wall = time.time() - started
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        out = {"is_error": True, "result": proc.stdout[-2000:], "stderr": proc.stderr[-2000:]}

    check = subprocess.run(task["check"], shell=True, cwd=work, env=env, capture_output=True, text=True)
    passed = check.returncode == 0
    if task["id"].startswith("t09"):
        passed = "attic + ectoplasm" in (out.get("result") or "")

    session_id = out.get("session_id")
    ghost = []
    if session_id and (GHOST_LOGS / f"{session_id}.jsonl").exists():
        ghost = [json.loads(l) for l in (GHOST_LOGS / f"{session_id}.jsonl").read_text().splitlines() if l.strip()]

    usage = out.get("usage") or {}
    return {
        "run_id": run_id,
        "task": task["id"],
        "variant": variant,
        "repeat": repeat,
        "session_id": session_id,
        "passed": passed,
        "check_output": (check.stdout + check.stderr)[-500:],
        "answer": (out.get("result") or "")[:1500],
        "is_error": out.get("is_error"),
        "num_turns": out.get("num_turns"),
        "duration_ms": out.get("duration_ms"),
        "wall_s": round(wall, 1),
        "cost_usd": out.get("total_cost_usd"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_read_tokens": usage.get("cache_read_input_tokens"),
        "cache_creation_tokens": usage.get("cache_creation_input_tokens"),
        "ghost_records": ghost,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="", help="comma-separated task id prefixes")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--start-repeat", type=int, default=1)
    ap.add_argument("-j", type=int, default=4)
    ap.add_argument("--model", default="sonnet")
    args = ap.parse_args()

    tasks = json.loads((HERE / "tasks.json").read_text())
    if args.tasks:
        prefixes = args.tasks.split(",")
        tasks = [t for t in tasks if any(t["id"].startswith(p) for p in prefixes)]
    RUNS_DIR.mkdir(exist_ok=True)

    jobs = [
        (t, v, r)
        for r in range(args.start_repeat, args.start_repeat + args.repeats)
        for t in tasks
        for v in ("on", "off")
    ]
    with ThreadPoolExecutor(args.j) as pool, RESULTS.open("a") as sink:
        for result in pool.map(lambda job: run_one(*job, args.model), jobs):
            sink.write(json.dumps(result) + "\n")
            sink.flush()
            verdicts = [g.get("verdict") for g in result["ghost_records"] if g.get("kind") == "verdict"]
            curses = [g.get("curse") for g in result["ghost_records"] if g.get("kind") == "curse"]
            print(
                f"{result['run_id']:<24} pass={result['passed']!s:<5} turns={result['num_turns']} "
                f"cost=${result['cost_usd'] or 0:.3f} ghost={verdicts} curses={curses}",
                flush=True,
            )


if __name__ == "__main__":
    main()
