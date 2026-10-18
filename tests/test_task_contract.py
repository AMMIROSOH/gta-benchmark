import copy
import json
from pathlib import Path
import unittest

from sa_agent.tasks import TaskEvaluator, load_task, preconditions, validate_task

ROOT = Path(__file__).resolve().parents[1]


def state(counter=1):
    return {"sample_count": counter, "game_time_ms": counter * 100,
        "player": {"position": {"x": 0, "y": 0, "z": 0}, "in_vehicle": False,
            "health": 100, "speed_mps": 0, "wanted_level": 0},
        "vehicle": None, "world": {"player_state": 0, "nearby_vehicles": []}}


class TaskContractTests(unittest.TestCase):
    def task(self):
        return json.loads((ROOT / "tasks/01_steal_car.json").read_text(encoding="utf-8"))

    def test_sample_pack_contains_baselines_with_unique_ids(self):
        tasks = [load_task(str(path)) for path in sorted((ROOT / "tasks").glob("*.json"))]
        identifiers = {task["id"] for task in tasks}
        self.assertTrue({"steal_car", "walk_to_waypoint", "drive_100m", "park_and_exit", "lose_wanted"} <= identifiers)
        self.assertEqual(len(tasks), len(identifiers))

    def test_rejects_ambiguous_or_unusable_rules(self):
        changes = [
            {"version": True}, {"timeout_seconds": float("nan")},
            {"allowed_actions": ["idle", "idle", "enter_exit"]},
            {"preconditions": {"on_foot": True, "driving_automobile": True}},
            {"success": {"type": "enter_car_as_driver", "hold_seconds": -1}},
            {"success": {"type": "enter_car_as_driver", "hold_seconds": 2, "typo": 1}},
            {"allowed_actions": ["idle", "invented_action"]},
        ]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_task({**self.task(), **change})

    def test_bicycle_or_passenger_seat_cannot_satisfy_car_task(self):
        task, initial = self.task(), state()
        for car in ({"vehicle_class": 10, "is_driver": True, "health": 1000},
                    {"vehicle_class": 0, "is_driver": False, "health": 1000}):
            evaluator = TaskEvaluator(task, initial)
            observed = state(2)
            observed["player"]["in_vehicle"] = True
            observed["vehicle"] = car
            self.assertFalse(evaluator.evaluate(observed, 0).success)
            observed["sample_count"] = 3
            self.assertFalse(evaluator.evaluate(observed, 10).success)

    def test_driver_hold_needs_fresh_samples_and_resets_on_suspension(self):
        evaluator = TaskEvaluator(self.task(), state())
        observed = state(2)
        observed["player"]["in_vehicle"] = True
        observed["vehicle"] = {"vehicle_class": 0, "is_driver": True, "health": 1000}
        self.assertFalse(evaluator.evaluate(observed, 0).success)
        self.assertFalse(evaluator.evaluate(observed, 3).success)  # Same sample cannot advance a hold.
        evaluator.suspend()
        observed["sample_count"] = 3
        self.assertFalse(evaluator.evaluate(observed, 3).success)
        observed["sample_count"] = 4
        self.assertTrue(evaluator.evaluate(observed, 5).success)

    def test_fresh_new_game_does_not_satisfy_manual_driving_setup(self):
        task = load_task("drive_100m")
        self.assertIn("Start as an automobile's driver", preconditions(task, state()))

    def test_distance_task_rejects_teleport_and_changed_vehicle(self):
        task = load_task("drive_100m")
        initial = state()
        initial["player"]["in_vehicle"] = True
        initial["vehicle"] = {"vehicle_class": 0, "is_driver": True, "health": 1000, "reference": 257}
        changed = copy.deepcopy(initial)
        changed["sample_count"] = 2
        changed["game_time_ms"] = 200
        changed["player"]["position"]["x"] = 1000
        self.assertEqual("position_discontinuity", TaskEvaluator(task, initial).evaluate(changed, 1).failure)
        changed["vehicle"]["reference"] = 258
        self.assertEqual("left_or_changed_starting_vehicle", TaskEvaluator(task, initial).evaluate(changed, 1).failure)
