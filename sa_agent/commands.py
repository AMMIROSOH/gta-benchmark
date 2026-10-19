"""Agent-owned actions with finite authorization horizons and short native leases."""

import math
import copy
from . import movement
from .actions import ACTIONS, available_actions

INTERFACE = "agent_actions_v1"
EXECUTOR_VERSION = "interruptible_pad_v1"
DURATIONS_MS = (3000,)
MAX_DURATION_MS = 3000
GOAL_DISTANCE_M = 20.0
PULSES = {"jump", "enter_exit", "weapon_next", "weapon_previous"}


def uses_agent_actions(task):
    return task.get("action_interface") == INTERFACE


def observation(state):
    value = movement.observation(state)
    value["observation_interface"] = INTERFACE
    geometry = {v["reference"]: v for v in state["navigation"]["vehicles"]}
    for vehicle in value["world"]["nearby_vehicles"]:
        raw = geometry.get(vehicle["reference"], {})
        for key in ("driver_door", "driver_door_valid", "door_busy", "lock_status"):
            if key in raw:
                vehicle[key] = raw[key]
        locks = ("not_used", "unlocked", "locked", "lockout_player_only", "locked_player_inside",
                 "cop_car", "force_shut_doors", "skip_shut_doors")
        lock = raw.get("lock_status")
        if type(lock) is int and 0 <= lock < len(locks):
            vehicle["lock_status_name"] = locks[lock]
    value["player"]["entering_vehicle"] = state["navigation"].get("entering_vehicle", False)
    if state.get("actors"):
        # This mapping contains engine facts and attributed death events, no targets or strategies.
        value["actors"] = copy.deepcopy(state["actors"])
    return value


def choice_commands(task, state):
    result = {}
    for action in available_actions(task, state):
        durations = (400,) if action in PULSES else DURATIONS_MS
        directions = range(16) if action in movement.MOVEMENT_ACTIONS else (None,)
        for index in directions:
            for duration in durations:
                parameters = {"duration_ms": duration}
                if index is not None:
                    angle = index * math.tau / 16
                    parameters["direction_world_xy"] = {
                        "x": round(math.sin(angle), 8), "y": round(math.cos(angle), 8)}
                name = f"{action}_" + (f"d{index:02}_" if index is not None else "") + f"{duration}ms"
                result[name] = {"action": action, "parameters": parameters}
    return result


def execution(action, parameters, state):
    moving = action in movement.MOVEMENT_ACTIONS
    fields = {"duration_ms", "direction_world_xy"} if moving else {"duration_ms"}
    if action not in ACTIONS or not isinstance(parameters, dict) or set(parameters) != fields:
        raise ValueError("Invalid agent action or parameters")
    duration = parameters["duration_ms"]
    limit = 400 if action in PULSES else MAX_DURATION_MS
    if type(duration) is not int or not 1 <= duration <= limit:
        raise ValueError(f"duration_ms must be an integer in 1..{limit}")
    # Reuse strict unit-vector/mode validation, preserving the historical v1 executor.
    if moving:
        _, short_goal = movement.execution(action, {**parameters, "duration_ms": 1}, state)
        position = state["player"]["position"]
        goal = {axis: position[axis] + parameters["direction_world_xy"][axis]*GOAL_DISTANCE_M
                for axis in ("x", "y")}
        if not all(math.isfinite(v) and abs(v) <= 6000 for v in goal.values()):
            raise ValueError("Movement endpoint is outside game-coordinate bounds")
        return duration, {**goal, "z": short_goal["z"], "stop_radius_m": .1}
    return duration, None


class AuthorizedCommand:
    """Keep one frozen command alive only until its agent-authorized deadline.

    Every renewal has <=300 ms of native authority. No route, target tracking,
    retries, sensor-based correction or extension of the authorization occurs.
    """
    def __init__(self, action, parameters, goal, now, duration_ms, command_id, in_vehicle):
        self.action, self.parameters, self.goal = action, copy.deepcopy(parameters), copy.deepcopy(goal)
        self.deadline = now + duration_ms / 1000
        self.next_lease = now
        self.command_id, self.in_vehicle = command_id, in_vehicle

    def lease(self, now, in_vehicle):
        if now >= self.deadline or in_vehicle != self.in_vehicle:
            return None
        if now < self.next_lease:
            return None
        remaining = int((self.deadline-now)*1000)
        if remaining < 1:
            return None
        self.next_lease = self.deadline if self.action in PULSES else now + .1
        return min(400 if self.action in PULSES else 300, remaining)

    def describe(self, now):
        return copy.deepcopy({"command_id": self.command_id, "action": self.action,
                "parameters": self.parameters, "goal": self.goal,
                "remaining_ms": max(0, round((self.deadline-now)*1000))})
