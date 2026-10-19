"""Task-independent observations and bounded movement execution; no path planning."""

import copy
import math

INTERFACE = "bounded_movement_v1"
EXECUTOR_VERSION = "world_input_v1"
DURATIONS_MS = (200, 400, 600)
MAX_DURATION_MS = 750
GOAL_DISTANCE_M = 3.0
MOVEMENT_ACTIONS = {"world_walk", "world_run", "world_sprint"}
SUPPORTED_ACTIONS = MOVEMENT_ACTIONS | {"idle", "jump"}


def uses_bounded_movement(task):
    return task.get("action_interface") == INTERFACE


def observation(state):
    """Publish geometry facts, without car suitability, route costs or controller advice."""
    nav = state["navigation"]
    geometry = {v["reference"]: v for v in nav["vehicles"]}
    fields = ("reference", "model_id", "kind", "position", "heading_radians", "health",
              "speed_mps", "occupied", "velocity_xy", "right_xy", "forward_xy",
              "half_width", "front_extent", "rear_extent")
    vehicles = []
    for vehicle in state["world"]["nearby_vehicles"]:
        raw = {**vehicle, **geometry.get(vehicle["reference"], {})}
        vehicles.append({key: raw[key] for key in fields if key in raw})
    rays = [{"direction_world_xy": {"x": -math.sin(r["heading_radians"]),
                                    "y": math.cos(r["heading_radians"])},
             "clearance_m": r["clearance_m"], "ground_delta_m": r["ground_delta_m"]}
            for r in nav["rays"]]
    return copy.deepcopy({
        "observation_interface": INTERFACE,
        "sample_count": state["sample_count"], "game_time_ms": state["game_time_ms"],
        "player": state["player"], "vehicle": state.get("vehicle"),
        "clock": state.get("clock"), "weather": state.get("weather"),
        "world": {"sample_age_ms": state["world"]["sample_age_ms"],
            "camera_forward_xy": state["world"]["camera_forward_xy"],
            "nearby_vehicles": sorted(vehicles, key=lambda v: v["reference"])},
        "navigation": {"sample_age_ms": nav["sample_age_ms"], "rays": rays,
            "nodes": [{key: node[key] for key in ("reference", "position", "road", "visible", "links")}
                      for node in sorted(nav["nodes"], key=lambda n: n["reference"])]},
    })


def choice_commands(task, state):
    """A fixed, unranked discretization for choice models; never filter by geometry/goal."""
    commands = {}
    for action in task["allowed_actions"]:
        if state["player"]["in_vehicle"] and action != "idle":
            continue
        if action in MOVEMENT_ACTIONS:
            for index in range(16):
                angle = index * math.tau / 16
                # Direction index 0 is +Y; index 4 is +X. These are world axes.
                direction = {"x": round(math.sin(angle), 8), "y": round(math.cos(angle), 8)}
                for duration in DURATIONS_MS:
                    commands[f"{action}_d{index:02}_{duration}ms"] = {
                        "action": action, "parameters": {"direction_world_xy": direction,
                                                          "duration_ms": duration}}
        else:
            for duration in DURATIONS_MS:
                commands[f"{action}_{duration}ms"] = {
                    "action": action, "parameters": {"duration_ms": duration}}
    return commands


def execution(action, parameters, state):
    """Validate one explicit command and translate it to the existing expiring pad lease.

    This function never reads the task goal, road graph, clearance, history or a target.
    The native bridge steers to one point at most 3 m away for at most 750 ms.
    It cannot renew the command, choose a detour or retry it.
    """
    moving = action in MOVEMENT_ACTIONS
    required = {"duration_ms", "direction_world_xy"} if moving else {"duration_ms"}
    if action not in SUPPORTED_ACTIONS or not isinstance(parameters, dict) or set(parameters) != required:
        raise ValueError("Invalid bounded movement action or parameters")
    duration = parameters["duration_ms"]
    if type(duration) is not int or not 1 <= duration <= MAX_DURATION_MS:
        raise ValueError("Movement duration must be an integer between 1 and 750 ms")
    if not moving:
        if action != "idle" and state["player"]["in_vehicle"]:
            raise ValueError("On-foot movement requires an on-foot player")
        return duration, None
    if state["player"]["in_vehicle"]:
        raise ValueError("On-foot movement requires an on-foot player")
    direction = parameters["direction_world_xy"]
    if not isinstance(direction, dict) or set(direction) != {"x", "y"} or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
            for v in direction.values()):
        raise ValueError("Movement direction must contain finite numeric x and y")
    if not math.isclose(math.hypot(direction["x"], direction["y"]), 1.0, abs_tol=1e-6):
        raise ValueError("Movement direction must be a unit vector")
    position = state["player"]["position"]
    goal = {axis: position[axis] + direction[axis] * GOAL_DISTANCE_M for axis in ("x", "y")}
    if not all(math.isfinite(v) and abs(v) <= 6000 for v in goal.values()):
        raise ValueError("Movement goal is outside the game-coordinate bounds")
    return duration, {**goal, "z": position["z"], "stop_radius_m": 0.1}
