"""Command-line entry point; importing this module never connects to GTA or Jev."""

import argparse
import json
import math
from pathlib import Path
import sys

from .config import ROOT, default_config_path, load_config, validate_config


def main():
    from . import __version__
    parser = argparse.ArgumentParser(description="GTA Benchmark: state-driven agent evaluation")
    parser.add_argument("--version", action="version", version=f"GTA Benchmark {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List task definitions")
    sub.add_parser("agents", help="List registered agent adapters without calling a model")
    validate = sub.add_parser("validate", help="Validate task definitions and config offline")
    validate.add_argument("--config", type=Path, default=default_config_path())
    run = sub.add_parser("run", help="Prepare and run one task, then record its aftermath on success")
    run.add_argument("task", help="Task ID or path to a task JSON file")
    run.add_argument("--config", type=Path, default=default_config_path())
    run.add_argument("--decision-hz", type=int, choices=(5, 10))
    run.add_argument("--model", help="A TypeSafe model ID; the actual response model is logged")
    run.add_argument("--timeout-seconds", type=float, help="Override this attempt's task timeout")
    run.add_argument("--output-dir", type=Path)
    run.add_argument("--reset", choices=("new_game", "none"), help="Override reset.mode for this attempt")
    run.add_argument("--post-success-seconds", type=float, help="Extra recording after success (default 15)")
    reset = sub.add_parser("reset", help="Start a fresh New Game and wait beside the opening bicycle; no agent or task")
    reset.add_argument("--config", type=Path, default=default_config_path())
    reset.add_argument("--output-dir", type=Path, default=ROOT / "runtime/resets")
    state = sub.add_parser("state", help="Read the local game and world state once")
    state.add_argument("--watch", action="store_true")
    state.add_argument("--summary", action="store_true", help="Show vehicle kinds, driver doors and navigation readiness")
    profile = sub.add_parser("profile", help="Generate the ASI INI from benchmark config; does not deploy it")
    profile.add_argument("--config", type=Path, default=default_config_path())
    results = sub.add_parser("results", help="Show terminal results from recorded runs")
    results.add_argument("--output-dir", type=Path, default=ROOT / "runs")
    args = parser.parse_args()
    try:
        if args.command == "agents":
            from .agents import AGENTS
            for name in sorted(AGENTS):
                print(name)
            return
        if args.command == "validate":
            from .tasks import load_task
            load_config(args.config)
            checked = [load_task(str(path)) for path in sorted((ROOT / "tasks").rglob("*.json"))]
            ids = [task["id"] for task in checked]
            if len(ids) != len(set(ids)):
                raise ValueError("Task IDs must be unique")
            print(json.dumps({"status": "valid", "config": str(args.config), "tasks": ids}, indent=2))
            return
        if args.command == "list":
            for file in sorted((ROOT / "tasks").glob("*.json")):
                task = json.loads(file.read_text(encoding="utf-8"))
                print(f"{task['id']:22} {task['timeout_seconds']:>3}s  {task['title']}")
                print(f"  Setup: {task['setup']}")
            return
        if args.command == "profile":
            config = load_config(args.config)
            game = config["game"]
            path = ROOT / "configs/SAAgentTelemetry.ini"
            path.write_text(
                "[Benchmark]\nEnabled=1\n"
                f"Width={game['width']}\nHeight={game['height']}\nFPSCap={game['fps_cap']}\n"
                "TelemetryHz=10\nNearbyVehicleRadius=80\n\n"
                "[Control]\nEnabled=1\nMaxActionMilliseconds=750\n", encoding="utf-8")
            windowed = ROOT / "configs/III.VC.SA.WindowedMode.ini"
            windowed.write_text(
                "[window]\nmode=1\nwindowedStyle=1\nmaximized=0\n"
                f"resolutionX={game['width']}\nresolutionY={game['height']}\n"
                "positionX=-1\npositionY=-1\n\n[game]\nautoPause=1\nautoResume=1\n",
                encoding="utf-8")
            print(f"Wrote {path} and {windowed}. Install both profiles and restart GTA to apply them.")
            return
        if args.command == "results":
            for file in sorted(args.output_dir.glob("*/*/result.json")):
                result = json.loads(file.read_text(encoding="utf-8"))
                score = f" score={result['score']} {result['score_unit']}" if "score" in result else ""
                print(f"{result['task_id']:22} {result['status']:10} {result['elapsed_seconds']:8.2f}s  {result['reason']}{score}  {file.parent}")
            return
        if sys.platform != "win32":
            raise RuntimeError("Game access and task recording require Windows")
        if args.command == "state":
            import time
            from .game import GameClient
            client = GameClient()
            while True:
                value = client.read()
                if args.summary:
                    nav = value.get("navigation") or {}
                    value = {"status": value["status"], "player": value["player"],
                        "navigation_age_ms": nav.get("sample_age_ms"),
                        "world_goals_ready": nav.get("world_goals_ready", False),
                        "road_nodes": sum(n["road"] for n in nav.get("nodes", [])),
                        "pedestrian_nodes": sum(not n["road"] for n in nav.get("nodes", [])),
                        "clearance_rays": len(nav.get("rays", [])),
                        "nearby_vehicles": [{k: v[k] for k in ("reference", "model_id", "kind", "distance_m",
                            "speed_mps", "driver_door") if k in v} for v in value["world"]["nearby_vehicles"]]}
                print(json.dumps(value, indent=None if args.watch else 2, allow_nan=False), flush=True)
                if not args.watch:
                    return
                time.sleep(0.2)
        if args.command == "reset":
            from datetime import datetime, timezone
            import uuid
            from .game import ControlBridge
            from .lifecycle import ensure_game_running, reset_new_game
            config = load_config(args.config)
            if config["reset"]["mode"] != "new_game":
                raise ValueError("The reset command requires reset.mode=new_game in its config")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:8]
            directory = args.output_dir.resolve() / stamp
            process_info = ensure_game_running(config["reset"])
            with ControlBridge() as controls:
                preparation, _, _ = reset_new_game(config, controls, directory, process_info)
            print(json.dumps({"status": preparation["status"],
                "elapsed_seconds": preparation["elapsed_seconds"], "reset": str(directory / "reset.json")}, indent=2))
            return
        if args.command == "run":
            from .tasks import load_task
            config = load_config(args.config)
            if args.decision_hz:
                config["agent"]["decision_hz"] = args.decision_hz
            if args.model:
                config["agent"]["model"] = args.model
            if args.reset:
                config["reset"]["mode"] = args.reset
            if args.post_success_seconds is not None:
                if not math.isfinite(args.post_success_seconds) or not 0 <= args.post_success_seconds <= 120:
                    raise ValueError("post-success-seconds must be finite and between 0 and 120")
                config["recording"]["post_success_seconds"] = args.post_success_seconds
            validate_config(config)
            output_root = args.output_dir or Path(config["output_dir"])
            if not output_root.is_absolute():
                output_root = ROOT / output_root
            from .runner import run_task
            task = load_task(args.task)
            if args.timeout_seconds is not None:
                if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
                    raise ValueError("timeout-seconds must be finite and positive")
                task["timeout_seconds"] = args.timeout_seconds
            from .tasks import validate_task
            validate_task(task)
            result, directory = run_task(task, config, output_root)
            print(json.dumps({"status": result["status"], "reason": result["reason"],
                              **({"error": result["error"]} if result.get("error") else {}),
                              **({"precondition_failures": result["precondition_failures"]}
                                 if result.get("precondition_failures") else {}),
                              "elapsed_seconds": result["elapsed_seconds"],
                              **({k: result[k] for k in ("score", "score_unit", "score_complete")} if "score" in result else {}),
                              "result": str(directory / "result.json"),
                              "video": (result.get("video") or {}).get("path")}, indent=2))
            raise SystemExit(0 if result["status"] in {"success", "completed"} else 1)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f"gta-benchmark: {error}", file=sys.stderr)
        raise SystemExit(2)
