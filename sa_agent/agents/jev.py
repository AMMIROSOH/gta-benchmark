"""TypeSafe Jev integration: game-state JSON in, one allowed control choice out."""

from collections import deque
import math
import os
import time

from ..actions import available_actions
from ..movement import INTERFACE, choice_commands, uses_bounded_movement
from .base import Decision
from ..private_env import load_typesafe_key
from ..typesafe_http import request_json
from .. import commands as agent_commands


class JevAgent:
    def __init__(self, config):
        load_typesafe_key()
        self.config = config
        self.key = os.environ.get(config["api_key_env"], "")
        if not self.key or self.key.startswith("replace-"):
            raise ValueError(f"Set {config['api_key_env']} to a TypeSafe API key before running Jev")
        if config["endpoint"] != "https://api.typesafe.ai/v1/systemone":
            raise ValueError("This agent uses TypeSafe's official endpoint; change the adapter for another provider")
        self.history = deque(maxlen=config["history_size"])

    def decide(self, task, state, elapsed, progress, observation_time):
        if agent_commands.uses_agent_actions(task):
            return self.choose_movement(task, state, elapsed, progress, observation_time)
        if uses_bounded_movement(task):
            return self.choose_movement(task, state, elapsed, progress, observation_time)
        if task["success"]["type"] == "enter_car_as_driver":
            return self.choose_car(task, state, elapsed, progress, observation_time)
        options = available_actions(task, state)
        context = {
            "environment": "GTA San Andreas single-player",
            "task": {"id": task["id"], "instruction": task["instruction"],
                     "success_rule": task["success"], "elapsed_seconds": round(elapsed, 3),
                     "remaining_seconds": max(0, round(task["timeout_seconds"] - elapsed, 3))},
            "game": {key: state[key] for key in ("player", "vehicle", "world", "clock", "weather")},
            "progress": progress, "recent_decisions": list(self.history),
            "control_semantics": {
                "duration_ms": self.config["action_duration_ms"],
                "on_foot": "Movement directions are relative to camera_forward_xy. Vehicle steering is relative to the car.",
                "coordinates": "Metres in world XYZ; bearing zero is +Y and positive turns toward -X.",
                "obstacles": "Obstacle probes are relative to PLAYER heading, not camera. Only buildings and objects are probed.",
                "scope": "Only the loaded vehicles within the bridge radius are listed. No navigation mesh or global map is supplied."
            }
        }
        payload = {"model": self.config["model"], "state": context, "questions": {
            "next_action": {"type": "choice",
                "instructions": "Which ONE allowed short control action best advances the stated GTA task from this game state? Use recent decisions to avoid repeating actions that make no progress. Select idle only when waiting is useful. Task success is judged by the host, not by you.",
                "criteria": options}}}
        started = time.monotonic()
        body = request_json(self.config["endpoint"], self.key,
                            self.config["request_timeout_seconds"], payload,
                            proxy=self.config.get("proxy"))
        answer = body.get("answers", {}).get("next_action", {})
        action = answer.get("choice")
        confidence = answer.get("confidence")
        probabilities = answer.get("probabilities")
        if (answer.get("type") != "choice" or action not in options or
            not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or
            not 0 <= confidence <= 1 or not isinstance(probabilities, dict)):
            raise RuntimeError("Invalid TypeSafe choice response; no action applied")
        if set(probabilities) != set(options) or any(
            not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1
            for p in probabilities.values()):
            raise RuntimeError("Invalid TypeSafe probability distribution")
        if not math.isclose(sum(probabilities.values()), 1.0, abs_tol=0.02):
            raise RuntimeError("TypeSafe probability distribution does not sum to one")
        if confidence < self.config["minimum_confidence"]:
            action = "idle"
        self.history.append({"action": action, "confidence": confidence,
                             "position": state["player"]["position"],
                             "in_vehicle": state["player"]["in_vehicle"]})
        return Decision(action, confidence, probabilities, body.get("model", self.config["model"]),
                        body.get("usage", {}), observation_time, time.monotonic() - started, tuple(options))

    def choose_movement(self, task, state, elapsed, progress, observation_time):
        extended = agent_commands.uses_agent_actions(task)
        interface = agent_commands.INTERFACE if extended else INTERFACE
        if state.get("observation_interface") != interface:
            raise ValueError("Bounded movement requires the shared observation interface")
        commands = (agent_commands.choice_commands if extended else choice_commands)(task, state)
        context = {
            "task": {"id": task["id"], "instruction": task["instruction"],
                "success_rule": task["success"], "elapsed_seconds": round(elapsed, 3),
                "remaining_seconds": max(0, round(task["timeout_seconds"] - elapsed, 3))},
            "observation": state, "progress": progress, "recent_decisions": list(self.history),
            "previous_request_latency_seconds": getattr(self, "last_request_latency", None),
            "action_semantics": {
                "interface": INTERFACE,
                "movement": "direction_world_xy is a unit vector in world axes, independent of the camera. Each command moves toward a point 3 metres in that direction for the chosen duration, then releases. It may stop earlier if the point is reached. Movement has normal game collisions.",
                "execution": "The host executes only your selected command. It does not plan a route, avoid obstacles, choose a waypoint, repeat movement or recover when blocked. You must choose the next action from the next observation.",
                "jump": "Press jump/climb while moving forward relative to camera_forward_xy for the chosen duration.",
                "geometry": "Each ray gives its world direction, clearance in metres and ground height delta. Nodes contain local road/pedestrian positions, line-of-sight visibility and links; no route is selected. Nearby vehicle geometry is unfiltered by suitability. Observations cover only the local loaded area.",
                "timing": "duration_ms is the time the button is held, not the interval between observations. Model requests can take seconds, during which expired inputs remain released. Choose direction, pace AND duration to make useful progress within the remaining wall time; shorter inputs cause more idle time between movements. Inputs are never renewed by the host.",
            },
        }
        if extended:
            context["available_controls"] = available_actions(task, state)
            context["action_semantics"].update({
                "interface": interface,
                "movement": "direction_world_xy is a unit vector in world axes. Normal pad input moves toward a fixed point 20 metres in that direction for your chosen duration. Collisions apply. The endpoint never tracks an entity or changes during a command.",
                "execution": "You own routes, vehicle choice, interception, entry attempts, combat, recovery and waiting. The host only executes one explicit command, monitors validity and judges results. enter_exit presses the normal game button once; the game chooses the nearby door and runs its normal entry animation. There is no host retry or target selection.",
                "timing": "Your command continues while the next model request runs and ends at its authorized duration (at most 3000 ms). A new accepted decision immediately interrupts it; you do not have to wait for the old duration to finish. previous_request_latency_seconds measures the last request. A hold SHORTER than request latency necessarily causes a stop before the next response. Choose a horizon covering request latency when you intend continuous input, and short holds when you deliberately want precision or a pause. Short native leases refresh only within your fixed authorization. Stale/invalid decisions, errors, pause, focus loss, death and deadline cancel it. current_command describes input active at observation time. Expired inputs stay released.",
                "combat": "attack presses fire/melee, aim holds normal game targeting (including the game's own aim assistance), aim_attack holds both. aim_left/right/up/down hold aim plus right-stick input. weapon_next/previous cycle once. No host aiming, pursuit, attack retry, weapon grant or target snapping exists. Cash pickups are collected by ordinary movement.",
            })
        payload = {"model": self.config["model"], "state": context, "questions": {
            "next_command": {"type": "choice", "criteria": commands,
                "instructions": "Choose ONE next command to accomplish the stated task using the current observation and previous decisions. You own navigation, obstacle handling, movement duration and waiting. Options describe commands, not recommended routes. Task success is judged by the host."}}}
        if extended:
            payload["questions"]["next_command"]["instructions"] = (
                "Choose ONE explicit held control. Continuous options authorize at most 3000 ms, "
                "but your next choice immediately replaces them. Choose idle to release/wait; "
                "interaction buttons are single pulses. You own route choice, target selection, "
                "approach, entry attempts, combat and recovery. The host only executes your command "
                "and judges task progress; it provides no navigation or retry policy.")
        started = time.monotonic()
        body = request_json(self.config["endpoint"], self.key,
            self.config["request_timeout_seconds"], payload, proxy=self.config.get("proxy"))
        answer = body.get("answers", {}).get("next_command", {})
        choice, confidence, probabilities = answer.get("choice"), answer.get("confidence"), answer.get("probabilities")
        if (answer.get("type") != "choice" or choice not in commands or
                isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or
                not math.isfinite(confidence) or not 0 <= confidence <= 1 or
                not isinstance(probabilities, dict) or set(probabilities) != set(commands) or any(
                    isinstance(p, bool) or not isinstance(p, (int, float)) or
                    not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities.values()) or
                not math.isclose(sum(probabilities.values()), 1, abs_tol=0.02)):
            raise RuntimeError("Invalid TypeSafe movement choice; no command accepted")
        command = commands[choice]
        if confidence < self.config["minimum_confidence"]:
            command = {"action": "idle", "parameters": {"duration_ms": 200}}
        self.last_request_latency = time.monotonic() - started
        self.history.append({**command, "selection": choice, "confidence": confidence,
            "request_latency_seconds": self.last_request_latency,
            "position": state["player"]["position"], "elapsed_seconds": round(elapsed, 3)})
        return Decision(command["action"], confidence, probabilities,
            body.get("model", self.config["model"]), body.get("usage", {}), observation_time,
            time.monotonic() - started, tuple(commands), parameters=command["parameters"])

    def choose_car(self, task, state, elapsed, progress, observation_time):
        navigation = progress["navigation_controller"]
        candidates = navigation["candidates"]
        options = {"wait": "No suitable car is reachable. Wait near the road for slow or stopped traffic."}
        for car in candidates:
            options[f"car_{car['reference']}"] = car
        payload = {"model": self.config["model"], "state": {
            "task": task["instruction"], "remaining_seconds": max(0, task["timeout_seconds"]-elapsed),
            "player": state["player"], "candidate_automobiles": candidates,
            "controller": {k: v for k, v in navigation.items() if k != "candidates"},
            "recent_selections": list(self.history),
            "execution": "A local controller follows road/pedestrian links, avoids obstacles, stands in front of slow moving traffic until it stops, walks around to the actual front-left driver door, presses F once, then waits for the entry animation. You select the target, not movement keys. Bicycles and motorcycles are deliberately excluded from the steal-car task."
        }, "questions": {"target_vehicle": {"type": "choice", "criteria": options,
            "instructions": "Select ONE specific reachable automobile to acquire. Prefer the lowest route cost, unlocked, parked or stopped car; an unoccupied car is easier. Choose moving traffic only when the listed front-interception strategy is feasible. Keep this target until entered, lost, or the controller reports a blocked route. Use wait only when no listed car is suitable. Never invent a vehicle or a location."}}}
        started = time.monotonic()
        body = request_json(self.config["endpoint"], self.key,
                            self.config["request_timeout_seconds"], payload,
                            proxy=self.config.get("proxy"))
        answer = body.get("answers", {}).get("target_vehicle", {})
        choice, confidence, probabilities = answer.get("choice"), answer.get("confidence"), answer.get("probabilities")
        if (answer.get("type") != "choice" or choice not in options or
                not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or
                not 0 <= confidence <= 1 or not isinstance(probabilities, dict) or
                set(probabilities) != set(options) or any(not isinstance(p, (int, float)) or
                not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities.values()) or
                not math.isclose(sum(probabilities.values()), 1, abs_tol=0.02)):
            raise RuntimeError("Invalid TypeSafe target selection; no target accepted")
        reference = int(choice.removeprefix("car_")) if choice != "wait" else None
        if confidence < self.config["minimum_confidence"]:
            reference = None
        self.history.append({"selected_vehicle_reference": reference, "confidence": confidence})
        return Decision("idle", confidence, probabilities, body.get("model", self.config["model"]),
            body.get("usage", {}), observation_time, time.monotonic()-started, tuple(options),
            {"type": "acquire_automobile", "target_vehicle_reference": reference,
             "selection": choice})
