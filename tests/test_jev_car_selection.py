from collections import deque
import time
import unittest
from unittest.mock import patch

from sa_agent.agents.jev import JevAgent
from sa_agent.navigation import candidate_cars
from test_navigation import fixture


class JevCarSelectionTests(unittest.TestCase):
    def agent(self):
        agent = object.__new__(JevAgent)
        agent.key = "test-credential-not-real"
        agent.config = {"model": "jev-1.14.0", "endpoint": "https://api.typesafe.ai/v1/systemone",
                        "request_timeout_seconds": 10, "minimum_confidence": 0}
        agent.history = deque(maxlen=8)
        return agent

    def test_jev_selects_a_committed_goal_instead_of_a_direction(self):
        state = fixture()
        progress = {"navigation_controller": {"phase": "select_target", "candidates": candidate_cars(state)}}
        def response(endpoint, key, timeout, payload, **kwargs):
            question = payload["questions"]["target_vehicle"]
            self.assertEqual({"wait", "car_257"}, set(question["criteria"]))
            self.assertNotIn("forward", question["criteria"])
            self.assertNotIn("frames", payload["state"])
            self.assertNotIn("nodes", payload["state"])
            return {"model": "jev-1.14.0", "answers": {"target_vehicle": {
                "type": "choice", "choice": "car_257", "confidence": .9,
                "probabilities": {"wait": .05, "car_257": .95}}}, "usage": {}}
        with patch("sa_agent.agents.jev.request_json", side_effect=response):
            decision = self.agent().choose_car({"instruction": "Steal a car", "timeout_seconds": 120},
                                               state, 0, progress, time.monotonic())
        self.assertEqual(257, decision.plan["target_vehicle_reference"])
        self.assertEqual("idle", decision.action)

    def test_unoffered_vehicle_is_rejected(self):
        state = fixture()
        progress = {"navigation_controller": {"candidates": candidate_cars(state)}}
        body = {"answers": {"target_vehicle": {"type": "choice", "choice": "car_999",
            "confidence": .9, "probabilities": {"wait": .05, "car_999": .95}}}}
        with patch("sa_agent.agents.jev.request_json", return_value=body):
            with self.assertRaisesRegex(RuntimeError, "Invalid TypeSafe target"):
                self.agent().choose_car({"instruction": "Steal a car", "timeout_seconds": 120},
                                        state, 0, progress, time.monotonic())
