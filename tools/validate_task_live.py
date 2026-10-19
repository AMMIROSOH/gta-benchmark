"""Explicit live integration fixture, never a model-performance benchmark.

Run only with --live. The fixture acts as an independent adapter through the
same public observation/Decision contract. Its navigation/combat policy is in
this test tool, never in the runner or executor. No game state is granted.
"""
import argparse
import math
import heapq
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sa_agent.agents.base import Decision
from sa_agent.config import load_config
from sa_agent.tasks import load_task


class FixtureAgent:
    def __init__(self, config):
        self.target = None
        self.entry_at = -100.
        self.motion_position = None
        self.motion_since = 0.

    def decide(self, task, state, elapsed, progress, observation_time):
        player = state["player"]
        position = player["position"]
        def choose(action, duration=1000, direction=None):
            if action.startswith("world_") and "jump" in task["allowed_actions"]:
                if self.motion_position is None or math.hypot(position["x"]-self.motion_position["x"],
                        position["y"]-self.motion_position["y"]) > .3:
                    self.motion_position, self.motion_since = dict(position), elapsed
                elif elapsed-self.motion_since > 1.5:
                    # Explicit recovery chosen by this diagnostic adapter, never the executor.
                    action, duration, direction = "jump", 400, None
                    self.motion_since = elapsed
            params = {"duration_ms": duration}
            if direction is not None:
                params["direction_world_xy"] = direction
            return Decision(action, None, None, "scripted-integration-fixture-v1", {},
                observation_time, time.monotonic()-observation_time, (), parameters=params)

        def distance(point):
            return math.hypot(point["x"]-position["x"], point["y"]-position["y"])

        def move(point, close=.8):
            length = distance(point)
            if length <= close:
                return choose("idle", 100)
            nodes = {n["reference"]: n for n in state["navigation"]["nodes"]}
            if length > 6 and nodes:
                # Dijkstra belongs to this explicitly scripted test adapter.
                # The runner still receives only the resulting bounded direction.
                starts = sorted((n for n in nodes.values() if n["visible"]),
                                key=lambda n: distance(n["position"]))[:4]
                destination = min(nodes, key=lambda ref: math.hypot(
                    nodes[ref]["position"]["x"]-point["x"], nodes[ref]["position"]["y"]-point["y"]))
                costs, frontier = {}, []
                for node in starts:
                    cost = distance(node["position"])
                    costs[node["reference"]] = cost
                    heapq.heappush(frontier, (cost, node["reference"], (node["reference"],)))
                while frontier:
                    cost, ref, path = heapq.heappop(frontier)
                    if cost > costs[ref]:
                        continue
                    if ref == destination:
                        next_node = next((nodes[r] for r in path if distance(nodes[r]["position"]) > 1.5), None)
                        if next_node:
                            point = next_node["position"]
                            length = distance(point)
                        break
                    for link in nodes[ref]["links"]:
                        if link not in nodes:
                            continue
                        a, b = nodes[ref]["position"], nodes[link]["position"]
                        candidate = cost+math.hypot(a["x"]-b["x"], a["y"]-b["y"])
                        if candidate < costs.get(link, math.inf):
                            costs[link] = candidate
                            heapq.heappush(frontier, (candidate, link, path+(link,)))
            direction = {axis: (point[axis]-position[axis])/length for axis in ("x", "y")}
            # This is explicitly the fixture adapter policy, outside execution/judgment.
            run_threshold = .95 if task["id"] in {"kill_npc", "earn_money"} else 5
            action = "world_run" if length > run_threshold else "world_walk"
            duration = max(100, min(1000, int((length-close)/3*1000)))
            return choose(action, duration, direction)

        if task["id"] == "drive_100m":
            heading = player["heading_radians"]
            forward = (-math.sin(heading), math.cos(heading))
            roads = [n["position"] for n in state["navigation"]["nodes"] if n["road"] and n["visible"]
                     and 8 < distance(n["position"]) < 35 and abs(n["position"]["z"]-position["z"]) < 3]
            if roads:
                def alignment(point):
                    return sum(forward[i]*(point[axis]-position[axis])/distance(point)
                               for i,axis in enumerate(("x", "y")))
                point = max(roads, key=lambda p: alignment(p)*.7+distance(p)/35*.3)
                dx, dy = point["x"]-position["x"], point["y"]-position["y"]
                cross = (forward[0]*dy-forward[1]*dx)/distance(point)
                return choose("accelerate_left" if cross > .2 else "accelerate_right" if cross < -.2 else "accelerate", 1000)
            return choose("accelerate", 1000)
        if task["id"] == "walk_to_waypoint":
            return move(task["success"]["position"], close=2.5)
        if task["id"] == "steal_car":
            if player["in_vehicle"] or player.get("entering_vehicle"):
                return choose("idle", 1000)
            cars = [c for c in state["world"]["nearby_vehicles"] if c.get("kind") == "automobile"
                and c.get("health", 0) > 300 and c.get("speed_mps", 100) < 1
                and c.get("driver_door_valid") and c.get("lock_status") in (0, 1)]
            if not cars:
                # Fixed, documented fixture staging policy: leave the opening alley.
                return move({"x": 2265, "y": -1260, "z": 24})
            car = next((c for c in cars if c["reference"] == self.target), min(cars, key=lambda c: distance(c["driver_door"])))
            self.target = car["reference"]
            if distance(car["driver_door"]) < 1.6:
                if elapsed-self.entry_at < 4:
                    return choose("idle", 1000)
                self.entry_at = elapsed
                return choose("enter_exit", 200)
            return move(car["driver_door"], close=1.2)
        actors = state["actors"]
        pickups = [p for p in actors["nearby_pickups"] if p["type"] in (8, 19)]
        if task["id"] == "earn_money" and pickups:
            return move(min(pickups, key=lambda p: distance(p["position"]))["position"], close=.1)
        # This fixture targets visible unarmed civilian NPCs. The benchmark itself
        # keeps every NPC and publishes these raw engine facts without filtering.
        peds = [p for p in actors["nearby_peds"] if p["health"] > 0 and not p["in_vehicle"]
                and p.get("visible") and p.get("ped_type") in (4, 5, 21, 22)
                and p.get("weapon_type") in (0, 1)
                and abs(p["position"]["z"]-position["z"]) < 3]
        if not peds:
            return move({"x": 2265, "y": -1250, "z": 24})
        ped = next((p for p in peds if p["reference"] == self.target), min(peds, key=lambda p: distance(p["position"])))
        self.target = ped["reference"]
        if distance(ped["position"]) > .95:
            return move(ped["position"], close=.6)
        # Normal repeated button presses chosen by the fixture, with explicit release.
        attack = "attack" if player["weapon_type"] in (0, 1) else "aim_attack"
        return choose(attack if int(elapsed*2) % 2 == 0 else "idle", 300)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=("steal_car", "walk_to_waypoint", "drive_100m", "kill_npc", "earn_money"))
    parser.add_argument("--live", action="store_true", required=True, help="Authorize real game/capture/input access")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--reset", choices=("none", "new_game"), default="none")
    parser.add_argument("--follow-with-drive", action="store_true", help="Immediately validate driving from a successful fixture acquisition")
    args = parser.parse_args()
    from sa_agent import agents, runner
    from sa_agent.provenance import file_hash
    agents.AGENTS["integration_fixture"] = ("__main__", "FixtureAgent")
    config = load_config(args.config)
    config["agent"].update(name="integration_fixture", model="scripted-integration-fixture-v1")
    config["reset"]["mode"] = args.reset
    config["recording"]["post_success_seconds"] = 0 if args.follow_with_drive else 3
    original_manifest = runner.make_manifest
    def manifest(*arguments):
        return {**original_manifest(*arguments), "validation_only": True,
                "fixture_policy_sha256": file_hash(__file__)}
    runner.make_manifest = manifest
    result, directory = runner.run_task(load_task(args.task), config, ROOT/"runs/validation-fixtures")
    print({"validation_only": True, "status": result["status"], "reason": result["reason"],
        "score": result.get("score"), "elapsed_seconds": result["elapsed_seconds"], "directory": str(directory)})
    if args.follow_with_drive and args.task == "steal_car" and result["status"] == "success":
        config["reset"]["mode"] = "none"
        config["game"]["startup_countdown_seconds"] = 0
        result, directory = runner.run_task(load_task("drive_100m"), config, ROOT/"runs/validation-fixtures")
        print({"validation_only": True, "status": result["status"], "reason": result["reason"],
            "elapsed_seconds": result["elapsed_seconds"], "directory": str(directory)})


if __name__ == "__main__":
    main()
