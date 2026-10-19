"""Audit bounded movement attribution and telemetry offline, optionally decode its video."""

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sa_agent.movement import EXECUTOR_VERSION, execution


def audit(directory, decode_video=False):
    directory = Path(directory).resolve()
    result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    task = json.loads((directory / "task.json").read_text(encoding="utf-8"))
    entries = [json.loads(line) for line in (directory / "actions.jsonl").read_text(encoding="utf-8").splitlines()]
    observations = [json.loads(line) for line in (directory / "observations.jsonl").read_text(encoding="utf-8").splitlines()]
    problems = []
    applied = [entry for entry in entries if entry.get("applied")]
    if result["policy_mode"] != "bounded_movement" or result["navigation_control_ticks"] != 0:
        problems.append("Unexpected policy mode or shared navigation ticks")
    if result["applied_actions"] != len(applied):
        problems.append("Applied input count does not match the decision trace")
    if not observations:
        problems.append("No scored observations")
    cursor = 0
    for index, entry in enumerate(applied):
        if entry.get("source") != "agent_action" or entry.get("executor_version") != EXECUTOR_VERSION:
            problems.append(f"Input {index} is not attributed to the bounded agent executor")
        while cursor+1 < len(observations) and observations[cursor+1]["elapsed_seconds"] <= entry["elapsed_seconds"]:
            cursor += 1
        current = observations[cursor]["state"] if observations else None
        if current is None:
            continue
        state = {"player": {"position": entry.get("execution_origin", current["player"]["position"]),
                            "in_vehicle": current["player"]["in_vehicle"]}}
        try:
            requested, goal = execution(entry["action"], entry.get("parameters"), state)
            duration = entry.get("duration_ms")
            if type(duration) is not int or not 1 <= duration <= requested:
                raise ValueError("Invalid leased duration")
            if entry["elapsed_seconds"] + duration/1000 > task["timeout_seconds"] + .002:
                raise ValueError("Lease exceeds the task deadline")
            actual = entry.get("goal")
            if goal is None:
                if actual is not None:
                    raise ValueError("Non-movement input contains a goal")
            elif not isinstance(actual, dict) or set(goal) != set(actual) or any(
                    not math.isclose(goal[k], actual[k], abs_tol=1e-6) for k in goal):
                raise ValueError("Executed goal differs from the agent direction projection")
            if entry.get("plan") is not None:
                raise ValueError("Input contains an unsupported execution plan")
        except (ValueError, KeyError, TypeError) as error:
            problems.append(f"Input {index}: {error}")
    acks = {o["state"]["world"]["last_applied_request"] for o in observations}
    latencies = [e["latency_seconds"] for e in entries if "latency_seconds" in e]
    position = task["success"]["position"]
    def distance(state):
        p = state["player"]["position"]
        return math.hypot(p["x"]-position["x"], p["y"]-position["y"])
    video_decoded = None
    if decode_video:
        config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
        video = (result.get("video") or {}).get("path")
        if not video:
            problems.append("No finalized video to decode")
        else:
            decoded = subprocess.run([config["recording"]["ffmpeg"], "-v", "error", "-xerror",
                "-i", video, "-f", "null", "-"], capture_output=True, text=True,
                creationflags=0x08000000 if sys.platform == "win32" else 0)
            video_decoded = decoded.returncode == 0 and not decoded.stderr.strip()
            if not video_decoded:
                problems.append("Video decode failed: " + decoded.stderr[-1000:])
    return {
        "run": str(directory), "task_version": result["task_version"],
        "status": result["status"], "reason": result["reason"],
        "elapsed_seconds": result["elapsed_seconds"],
        "initial_distance_m": distance(observations[0]["state"]) if observations else None,
        "final_distance_m": distance(result["final_state"]) if result.get("final_state") else None,
        "decisions": result["decision_count"], "applied_commands": len(applied),
        "navigation_control_ticks": result["navigation_control_ticks"],
        "observed_command_acknowledgements": sum(e.get("request_id") in acks for e in applied),
        "stale_drops": result["stale_decisions_dropped"],
        "invalid_drops": result["invalid_commands_dropped"],
        "leased_durations_ms": dict(Counter(str(e.get("duration_ms")) for e in applied)),
        "median_model_latency_seconds": statistics.median(latencies) if latencies else None,
        "video_decoded": video_decoded, "interface_audit_passed": not problems,
        "problems": problems,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--decode-video", action="store_true")
    args = parser.parse_args()
    report = audit(args.directory, args.decode_video)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["interface_audit_passed"] else 1)


if __name__ == "__main__":
    main()
