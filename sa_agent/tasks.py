"""Task loading, staging requirements, and deterministic game-state evaluators."""

from dataclasses import dataclass, field
import json
import math
import re
from pathlib import Path

from .actions import ACTIONS

ROOT = Path(__file__).resolve().parents[1]
KINDS = {"enter_car_as_driver", "reach_waypoint", "drive_distance", "park_and_exit", "wanted_zero"}


def validate_task(task, source="task"):
    """Reject ambiguous task definitions before connecting to a game or model."""
    def reject(message):
        raise ValueError(f"{source}: {message}")

    def number(value, name, minimum=0, inclusive=False):
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                not math.isfinite(value) or (value < minimum if inclusive else value <= minimum)):
            reject(f"{name} must be a finite number {'>=' if inclusive else '>'} {minimum}")

    if not isinstance(task, dict):
        reject("task must be an object")
    fields = {"$schema", "id", "version", "title", "instruction", "setup", "timeout_seconds",
              "preconditions", "success", "fail_on_death", "allowed_actions", "tags", "source_file"}
    if set(task)-fields:
        reject("unknown fields: " + ", ".join(sorted(set(task)-fields)))
    identifier = task.get("id")
    if not isinstance(identifier, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", identifier):
        reject("id must contain 1-64 letters, digits, underscores or hyphens")
    if type(task.get("version")) is not int or task["version"] < 1:
        reject("version must be a positive integer")
    for name in ("title", "instruction", "setup"):
        if not isinstance(task.get(name), str) or not task[name].strip():
            reject(f"{name} must be a nonempty string")
    number(task.get("timeout_seconds"), "timeout_seconds")
    if not isinstance(task.get("fail_on_death"), bool):
        reject("fail_on_death must be a boolean")
    actions = task.get("allowed_actions")
    if (not isinstance(actions, list) or not actions or
            any(not isinstance(action, str) or action not in ACTIONS for action in actions)):
        reject("allowed_actions must list known action names")
    if "idle" not in actions or len(actions) != len(set(actions)):
        reject("allowed_actions must include idle and contain no duplicates")
    required = task.get("preconditions")
    if not isinstance(required, dict):
        reject("preconditions must be an object")
    boolean_fields = {"on_foot", "driving_automobile", "nearby_automobile", "outside_goal"}
    if set(required) - boolean_fields - {"minimum_speed_mps", "minimum_wanted_level"}:
        reject("unknown precondition")
    if any(not isinstance(required[name], bool) for name in boolean_fields & required.keys()):
        reject("boolean preconditions must be true or false")
    if required.get("on_foot") and required.get("driving_automobile"):
        reject("on_foot and driving_automobile cannot both be required")
    if "minimum_speed_mps" in required:
        number(required["minimum_speed_mps"], "minimum_speed_mps", inclusive=True)
    if "minimum_wanted_level" in required and (type(required["minimum_wanted_level"]) is not int or
            not 0 <= required["minimum_wanted_level"] <= 6):
        reject("minimum_wanted_level must be an integer between 0 and 6")
    goal = task.get("success")
    if (not isinstance(goal, dict) or not isinstance(goal.get("type"), str)
            or goal["type"] not in KINDS):
        reject("success.type must name a registered evaluator")
    kind = goal["type"]
    goal_fields = {
        "enter_car_as_driver": {"hold_seconds"},
        "reach_waypoint": {"position", "radius_m", "vertical_tolerance_m", "hold_seconds"},
        "drive_distance": {"distance_m", "max_plausible_speed_mps"},
        "park_and_exit": {"stop_speed_mps", "stop_hold_seconds", "exit_hold_seconds", "near_car_radius_m"},
        "wanted_zero": {"hold_seconds"},
    }[kind]
    if set(goal) != {"type"} | goal_fields:
        reject(f"{kind} requires exactly: " + ", ".join(sorted(goal_fields)))
    for name in goal_fields - {"position"}:
        number(goal[name], f"success.{name}", inclusive=name in {"vertical_tolerance_m", "stop_speed_mps"})
    if kind == "reach_waypoint":
        position = goal["position"]
        if not isinstance(position, dict) or set(position) != {"x", "y", "z"}:
            reject("success.position must contain x, y and z")
        for axis, value in position.items():
            number(value, f"success.position.{axis}", minimum=-6000, inclusive=True)
            if value > 6000:
                reject("waypoint coordinates must be within -6000..6000")
    elif required.get("outside_goal"):
        reject("outside_goal is only supported by reach_waypoint")
    if kind == "enter_car_as_driver" and "enter_exit" not in actions:
        reject("car acquisition requires enter_exit")
    if kind != "enter_car_as_driver" and any(action.startswith("world_") for action in actions):
        reject("world-coordinate actions currently require the car acquisition controller")
    tags = task.get("tags", [])
    if (not isinstance(tags, list) or any(not isinstance(tag, str) or not tag.strip() for tag in tags)
            or len(tags) != len(set(tags))):
        reject("tags must be unique nonempty strings")
    return task


def load_task(identifier):
    explicit = Path(identifier)
    candidates = [explicit] if explicit.is_file() else list((ROOT / "tasks").glob("*.json"))
    for file in candidates:
        value = json.loads(file.read_text(encoding="utf-8"))
        validate_task(value, str(file))
        if explicit.is_file() or value["id"] == identifier:
            value["source_file"] = str(file.resolve())
            return value
    raise ValueError(f"Unknown task: {identifier}")


def horizontal_distance(a, b):
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def driving_car(state):
    vehicle = state.get("vehicle")
    return bool(vehicle and vehicle.get("is_driver") and vehicle.get("vehicle_class") == 0)


def preconditions(task, state):
    failures = []
    player = state.get("player")
    if not player or player["health"] <= 0:
        return ["Load a save with a living player"]
    required = task["preconditions"]
    if required.get("on_foot") and player["in_vehicle"]:
        failures.append("Start on foot")
    if required.get("driving_automobile") and not driving_car(state):
        failures.append("Start as an automobile's driver")
    if required.get("nearby_automobile") and not any(
        car["is_automobile"] and car["health"] > 0 for car in state["world"]["nearby_vehicles"]):
        failures.append("Start within the bridge radius of an automobile")
    if player["speed_mps"] < required.get("minimum_speed_mps", 0):
        failures.append(f"Starting speed must be at least {required['minimum_speed_mps']} m/s")
    if player["wanted_level"] < required.get("minimum_wanted_level", 0):
        failures.append(f"Start with at least {required['minimum_wanted_level']} wanted star(s)")
    goal = task["success"]
    if required.get("outside_goal") and horizontal_distance(player["position"], goal["position"]) <= goal["radius_m"]:
        failures.append("Start outside the waypoint success radius")
    return failures


@dataclass
class Verdict:
    success: bool = False
    failure: str | None = None
    progress: dict = field(default_factory=dict)


class TaskEvaluator:
    def __init__(self, task, initial):
        self.task, self.goal = task, task["success"]
        self.initial = initial
        self.previous = initial
        self.holds = {}
        self.distance = 0.0
        self.parked = False
        self.start_vehicle = (initial.get("vehicle") or {}).get("reference")
        self.last_counter = None
        self.last_verdict = Verdict()

    def suspend(self):
        self.holds.clear()

    def hold(self, name, condition, now, seconds):
        if not condition:
            self.holds.pop(name, None)
            return False
        start = self.holds.setdefault(name, now)
        return now - start >= seconds

    def evaluate(self, state, elapsed):
        if state["sample_count"] == self.last_counter:
            return self.last_verdict
        self.last_counter = state["sample_count"]
        player, vehicle = state["player"], state.get("vehicle")
        if self.task.get("fail_on_death") and (player["health"] <= 0 or state["world"]["player_state"] == 1):
            return Verdict(failure="player_died")
        if state["world"]["player_state"] == 2:
            return Verdict(failure="player_arrested")
        kind, goal = self.goal["type"], self.goal
        verdict = Verdict()
        if kind == "enter_car_as_driver":
            entered = driving_car(state) and vehicle["health"] > 0
            verdict.success = self.hold("driver", entered, elapsed, goal["hold_seconds"])
            verdict.progress = {"driving_automobile": entered,
                                "driver_hold_seconds": elapsed - self.holds.get("driver", elapsed)}
        elif kind == "reach_waypoint":
            distance = horizontal_distance(player["position"], goal["position"])
            inside = (not player["in_vehicle"] and distance <= goal["radius_m"] and
                      abs(player["position"]["z"] - goal["position"]["z"]) <= goal["vertical_tolerance_m"])
            verdict.success = self.hold("waypoint", inside, elapsed, goal["hold_seconds"])
            verdict.progress = {"distance_to_goal_m": distance, "goal": goal["position"]}
        elif kind == "drive_distance":
            if not driving_car(state) or vehicle["reference"] != self.start_vehicle:
                return Verdict(failure="left_or_changed_starting_vehicle")
            if vehicle["health"] <= 0:
                return Verdict(failure="vehicle_destroyed")
            dt_ms = (state["game_time_ms"] - self.previous["game_time_ms"]) & 0xFFFFFFFF
            step = horizontal_distance(player["position"], self.previous["player"]["position"])
            if dt_ms > 5000:
                return Verdict(failure="game_clock_discontinuity")
            if step > goal["max_plausible_speed_mps"] * dt_ms / 1000 + 2:
                return Verdict(failure="position_discontinuity")
            self.distance += step
            verdict.success = self.distance >= goal["distance_m"]
            verdict.progress = {"distance_driven_m": self.distance, "target_m": goal["distance_m"]}
        elif kind == "park_and_exit":
            car = next((item for item in state["world"]["nearby_vehicles"]
                        if item["reference"] == self.start_vehicle), None)
            if not car or car["health"] <= 0:
                return Verdict(failure="starting_vehicle_lost_or_destroyed")
            if player["in_vehicle"]:
                if not driving_car(state) or vehicle["reference"] != self.start_vehicle:
                    return Verdict(failure="changed_starting_vehicle")
                self.parked = self.hold("stopped", car["speed_mps"] <= goal["stop_speed_mps"],
                                        elapsed, goal["stop_hold_seconds"])
            elif not self.parked:
                return Verdict(failure="exited_before_parking")
            exited = (not player["in_vehicle"] and self.parked and
                      car["speed_mps"] <= goal["stop_speed_mps"] and
                      horizontal_distance(player["position"], car["position"]) <= goal["near_car_radius_m"])
            verdict.success = self.hold("exited", exited, elapsed, goal["exit_hold_seconds"])
            verdict.progress = {"parked": self.parked, "on_foot": not player["in_vehicle"],
                                "car_speed_mps": car["speed_mps"]}
        elif kind == "wanted_zero":
            verdict.success = self.hold("unwanted", player["wanted_level"] == 0,
                                        elapsed, goal["hold_seconds"])
            verdict.progress = {"wanted_level": player["wanted_level"],
                                "zero_hold_seconds": elapsed - self.holds.get("unwanted", elapsed)}
        self.previous = state
        self.last_verdict = verdict
        return verdict
