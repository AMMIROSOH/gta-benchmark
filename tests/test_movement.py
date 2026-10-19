"""Offline contracts: commands cannot silently acquire a route or autonomous recovery."""

from collections import deque
import json
import math
import unittest
from unittest.mock import patch

from sa_agent.agents.base import Decision
from sa_agent.agents.jev import JevAgent
from sa_agent.movement import choice_commands, execution, observation
from sa_agent.tasks import TaskEvaluator, load_task as current_task, validate_task


def load_task(identifier):
    # Preserve explicit coverage of the historical, non-renewing v1 contract.
    task = current_task(identifier)
    return {**task, "version": 2, "action_interface": "bounded_movement_v1"}


def snapshot():
    return {"sample_count": 1, "game_time_ms": 100,
        "player": {"position": {"x": 0, "y": 0, "z": 0}, "in_vehicle": False, "health": 100},
        "vehicle": None,
        "world": {"sample_age_ms": 0, "player_state": 0, "camera_forward_xy": {"x": 0, "y": 1},
            "nearby_vehicles": [{"reference": 257, "kind": "bicycle", "speed_mps": 15,
                "position": {"x": 1, "y": 0, "z": 0}, "health": 200}]},
        "navigation": {"sample_age_ms": 0, "world_goals_ready": True,
            "nodes": [{"reference": 4, "position": {"x": 1, "y": 2, "z": 0},
                       "road": False, "visible": True, "links": [5]}],
            "rays": [{"heading_radians": 0, "clearance_m": 0, "ground_delta_m": 0}],
            "vehicles": [{"reference": 257, "openable": False, "front_stop": {"x": 7},
                "door_anchors": [4], "front_anchors": [5], "half_width": 1}]}}


class MovementTests(unittest.TestCase):
    def test_task_versions_and_declared_interface_are_validated(self):
        task = load_task("walk_to_waypoint")
        self.assertEqual(2, task["version"])
        for change in ({"action_interface": "auto_walk"},
                       {"allowed_actions": ["idle", "forward"]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_task({**task, **change})
        old = {**task, "allowed_actions": ["idle", "forward"]}
        old.pop("action_interface")
        validate_task(old)  # Historical primitive tasks still work.
        with self.assertRaisesRegex(ValueError, "declared bounded"):
            validate_task({k: v for k, v in task.items() if k != "action_interface"})

    def test_observation_keeps_unsuitable_entities_but_removes_policy_hints(self):
        raw = snapshot()
        raw["navigation"]["route_cost_m"] = 2
        projected = observation(raw)
        encoded = json.dumps(projected)
        for forbidden in ("front_stop", "anchors", "openable", "route_cost", "controller"):
            self.assertNotIn(forbidden, encoded)
        self.assertEqual("bicycle", projected["world"]["nearby_vehicles"][0]["kind"])
        self.assertEqual(0, projected["navigation"]["rays"][0]["clearance_m"])
        self.assertEqual([5], projected["navigation"]["nodes"][0]["links"])
        projected["player"]["position"]["x"] = 999
        self.assertEqual(0, raw["player"]["position"]["x"])

    def test_menu_is_fixed_even_when_all_directions_are_blocked_or_goal_changes(self):
        task, raw = load_task("walk_to_waypoint"), snapshot()
        original = choice_commands(task, raw)
        self.assertEqual(102, len(original))
        for command in original.values():
            execution(command["action"], command["parameters"], raw)
        raw["navigation"]["rays"][0]["clearance_m"] = 8
        raw["player"]["position"]["x"] = 100
        task["success"]["position"]["x"] = -100
        self.assertEqual(original, choice_commands(task, raw))

    def test_executor_obeys_direction_despite_blocked_geometry_and_has_no_task_input(self):
        raw = snapshot()
        duration, goal = execution("world_run", {
            "direction_world_xy": {"x": 0, "y": 1}, "duration_ms": 400}, raw)
        self.assertEqual(400, duration)
        self.assertEqual({"x": 0, "y": 3, "z": 0, "stop_radius_m": .1}, goal)
        raw["navigation"] = None  # Execution does not consult sensors or calculate detours.
        self.assertEqual((duration, goal), execution("world_run", {
            "direction_world_xy": {"x": 0, "y": 1}, "duration_ms": 400}, raw))

    def test_executor_rejects_unbounded_or_ambiguous_commands(self):
        base = {"direction_world_xy": {"x": 1, "y": 0}, "duration_ms": 400}
        bad = [None, {**base, "duration_ms": 751}, {**base, "duration_ms": True},
            {**base, "duration_ms": 0}, {**base, "duration_ms": 400.0},
            {**base, "target": 257}, {**base, "direction_world_xy": {"x": 0, "y": 0}},
            {**base, "direction_world_xy": {"x": True, "y": 0}},
            {**base, "direction_world_xy": {"x": math.nan, "y": 0}},
            {**base, "direction_world_xy": {"x": math.inf, "y": 0}},
            {**base, "direction_world_xy": {"x": 1, "y": 0, "z": 0}}]
        for parameters in bad:
            with self.subTest(parameters=parameters), self.assertRaises(ValueError):
                execution("world_walk", parameters, snapshot())
        raw = snapshot()
        raw["player"]["in_vehicle"] = True
        with self.assertRaises(ValueError):
            execution("world_walk", base, raw)
        self.assertEqual((750, None), execution("idle", {"duration_ms": 750}, raw))

    def test_waypoint_hold_requires_on_foot_fresh_samples_and_correct_height(self):
        task, raw = load_task("walk_to_waypoint"), snapshot()
        task["success"].update(position={"x": 0, "y": 0, "z": 0}, radius_m=1)
        evaluator = TaskEvaluator(task, raw)
        self.assertFalse(evaluator.evaluate(raw, 0).success)
        self.assertFalse(evaluator.evaluate(raw, 2).success)  # Stale sample.
        raw["sample_count"] += 1
        raw["player"]["position"]["z"] = 10
        self.assertFalse(evaluator.evaluate(raw, 2).success)
        raw["sample_count"] += 1
        raw["player"]["position"]["z"] = 0
        self.assertFalse(evaluator.evaluate(raw, 3).success)
        raw["sample_count"] += 1
        raw["player"]["in_vehicle"] = True
        self.assertFalse(evaluator.evaluate(raw, 4).success)
        raw["sample_count"] += 1
        raw["player"]["in_vehicle"] = False
        self.assertFalse(evaluator.evaluate(raw, 5).success)
        raw["sample_count"] += 1
        self.assertTrue(evaluator.evaluate(raw, 6).success)


class JevMovementTests(unittest.TestCase):
    def agent(self):
        agent = object.__new__(JevAgent)
        agent.config = {"model": "jev-1.14.0", "endpoint": "https://api.typesafe.ai/v1/systemone",
                        "request_timeout_seconds": 10, "minimum_confidence": 0}
        agent.key = "test-credential-not-real"
        agent.history = deque(maxlen=8)
        return agent

    def response(self, payload, choice):
        options = payload["questions"]["next_command"]["criteria"]
        return {"model": "jev-1.14.0", "answers": {"next_command": {
            "type": "choice", "choice": choice, "confidence": .9,
            "probabilities": {key: float(key == choice) for key in options}}}}

    def test_model_selects_direction_and_duration_without_route_repair(self):
        task, raw = load_task("walk_to_waypoint"), snapshot()
        def reply(endpoint, key, timeout, payload, **kwargs):
            self.assertNotIn("frames", json.dumps(payload))
            self.assertNotIn("route_cost", json.dumps(payload))
            return self.response(payload, "world_walk_d04_400ms")
        with patch("sa_agent.agents.jev.request_json", side_effect=reply):
            decision = self.agent().decide(task, observation(raw), 0, {}, 100)
        self.assertEqual("world_walk", decision.action)
        self.assertEqual({"direction_world_xy": {"x": 1, "y": 0}, "duration_ms": 400}, decision.parameters)
        self.assertIsNone(decision.plan)
        self.assertEqual(100, decision.observation_time)

    def test_invented_choice_is_rejected(self):
        def reply(endpoint, key, timeout, payload, **kwargs):
            return self.response(payload, "navigate_to_goal")
        with patch("sa_agent.agents.jev.request_json", side_effect=reply), self.assertRaises(RuntimeError):
            self.agent().decide(load_task("walk_to_waypoint"), observation(snapshot()), 0, {}, 100)

    def test_non_jev_adapter_can_supply_parameters_without_probability_metadata(self):
        decision = Decision("world_walk", None, None, "other-agent", {}, 100, 0, (),
            parameters={"direction_world_xy": {"x": .6, "y": .8}, "duration_ms": 375})
        duration, goal = execution(decision.action, decision.parameters, snapshot())
        self.assertEqual(375, duration)
        self.assertAlmostEqual(1.8, goal["x"])
        self.assertAlmostEqual(2.4, goal["y"])


if __name__ == "__main__":
    unittest.main()
