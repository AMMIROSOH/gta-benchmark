"""Offline audit of agent authorizations, native leases and acknowledgements."""
import argparse
import json
import math
from pathlib import Path
import subprocess


def audit(directory, decode_video=False):
    directory = Path(directory)
    read = lambda name: json.loads((directory/name).read_text(encoding="utf-8"))
    result, task = read("result.json"), read("task.json")
    if task.get("action_interface") != "agent_actions_v1":
        raise ValueError("This audit requires agent_actions_v1")
    entries = [json.loads(line) for line in (directory/"actions.jsonl").read_text().splitlines()]
    observations = [json.loads(line) for line in (directory/"observations.jsonl").read_text().splitlines()]
    commands = {e["command_id"]: e for e in entries if e.get("source") == "agent_action" and e["applied"]}
    leases = [e for e in entries if e.get("source") == "authorized_command_lease"]
    if result["navigation_control_ticks"] != 0 or len(commands) != result["applied_actions"]:
        raise ValueError("Unattributed commands or shared navigation work")
    pulse = {"jump", "enter_exit", "weapon_next", "weapon_previous"}
    acknowledged = {e["state"]["world"]["last_applied_request"] for e in observations}
    confirmed, deadlines = set(), {}
    for command_id, command in commands.items():
        if command.get("plan") is not None or not 1 <= command["duration_ms"] <= 3000:
            raise ValueError("Invalid authorization")
        if command["action"].startswith("world_"):
            direction = command["parameters"]["direction_world_xy"]
            if not math.isclose(math.hypot(direction["x"], direction["y"]), 1, abs_tol=1e-6):
                raise ValueError("Non-unit direction")
            for axis in ("x", "y"):
                expected = command["execution_origin"][axis]+20*direction[axis]
                if not math.isclose(command["goal"][axis], expected, abs_tol=1e-6):
                    raise ValueError("Endpoint differs from the agent direction")
    for lease in leases:
        command = commands[lease["command_id"]]
        if lease["action"] != command["action"] or lease["goal"] != command["goal"]:
            raise ValueError("A renewal changed the authorized input")
        limit = 400 if lease["action"] in pulse else 300
        if not 1 <= lease["duration_ms"] <= limit:
            raise ValueError("Invalid native lease")
        end = lease["elapsed_seconds"]+lease["duration_ms"]/1000
        if end > min(lease["authorization_end_seconds"], task["timeout_seconds"])+1e-6:
            raise ValueError("A lease exceeds its authorization or task deadline")
        old = deadlines.setdefault(lease["command_id"], lease["authorization_end_seconds"])
        if old != lease["authorization_end_seconds"]:
            raise ValueError("Authorization was extended")
        if lease["request_id"] in acknowledged:
            confirmed.add(lease["command_id"])
    for command_id, command in commands.items():
        if command["action"] in pulse and sum(e["command_id"] == command_id for e in leases) != 1:
            raise ValueError("A pulse was repeated")
    # Union of actual authorization-limited lease intervals; superseding inputs overlap.
    covered, end = 0., 0.
    for lease in leases:
        start = lease["elapsed_seconds"]
        finish = min(start+lease["duration_ms"]/1000, lease["authorization_end_seconds"], result["elapsed_seconds"])
        covered += max(0, finish-max(start, end))
        end = max(end, finish)
    summary = {"run": str(directory.resolve()), "status": result["status"],
        "elapsed_seconds": result["elapsed_seconds"], "commands": len(commands),
        "native_leases": len(leases), "acknowledged_commands": len(confirmed),
        "input_coverage_seconds": covered, "input_coverage_fraction": covered/max(result["elapsed_seconds"], .001),
        "navigation_control_ticks": 0}
    if decode_video:
        config = read("config.json")
        subprocess.run([config["recording"]["ffmpeg"], "-v", "error", "-i", str(directory/"video.mp4"), "-f", "null", "-"], check=True)
        summary["video_decoded"] = True
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--decode-video", action="store_true")
    args = parser.parse_args()
    print(json.dumps(audit(args.directory, args.decode_video), indent=2))
