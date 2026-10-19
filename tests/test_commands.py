"""Agent authority, finite horizons, cross-provider actions and delayed execution."""
import copy
import json
import unittest
import sys
from unittest.mock import patch
from sa_agent import commands
from sa_agent.agents.base import Decision
from sa_agent.tasks import load_task
from test_movement import snapshot
import test_movement as legacy
import test_movement_episode as episodes


class CommandTests(unittest.TestCase):
    def test_unfiltered_entities_and_door_facts_without_target_policy(self):
        raw = snapshot()
        raw["navigation"]["vehicles"][0].update(driver_door={"x": 1, "y": 2, "z": 0}, lock_status=2)
        projected = commands.observation(raw)
        encoded = json.dumps(projected)
        self.assertEqual("bicycle", projected["world"]["nearby_vehicles"][0]["kind"])
        self.assertEqual(2, projected["world"]["nearby_vehicles"][0]["lock_status"])
        for forbidden in ("anchors", "route_cost", "front_stop", "openable", "candidates"):
            self.assertNotIn(forbidden, encoded)
        raw["actors"] = {"nearby_peds": [{"reference": 9, "ped_type": 7,
            "weapon_type": 31, "visible": False, "health": 100},
            {"reference": 10, "ped_type": 5, "weapon_type": 0, "visible": True, "health": 0}]}
        projected = commands.observation(raw)
        self.assertEqual(raw["actors"], projected["actors"])
        projected["actors"]["nearby_peds"].clear()
        self.assertEqual(2, len(raw["actors"]["nearby_peds"]))

    def test_long_authorization_never_moves_its_endpoint_or_extends_deadline(self):
        params = {"duration_ms": 2400, "direction_world_xy": {"x": 1, "y": 0}}
        duration, goal = commands.execution("world_run", params, snapshot())
        active = commands.AuthorizedCommand("world_run", params, goal, 10, duration, 1, False)
        for i in range(49):
            now = 10+i*.05
            lease = active.lease(now, False)
            if lease:
                self.assertLessEqual(now+lease/1000, 12.4+1e-9)
                self.assertLessEqual(lease, 300)
                self.assertEqual(20, active.goal["x"])
        self.assertIsNone(active.lease(12.401, False))
        self.assertIsNone(active.lease(10.1, True))
        exposed = active.describe(10)
        exposed["goal"]["x"] = 999
        exposed["parameters"]["direction_world_xy"]["x"] = -1
        self.assertEqual(20, active.goal["x"])
        self.assertEqual(1, active.parameters["direction_world_xy"]["x"])

    def test_edge_actions_receive_exactly_one_pulse(self):
        for action in commands.PULSES:
            active = commands.AuthorizedCommand(action, {"duration_ms": 400}, None, 10, 400, 1, False)
            leases = [active.lease(10+i*.05, False) for i in range(12)]
            self.assertEqual(1, sum(v is not None for v in leases))
            with self.assertRaises(ValueError):
                commands.execution(action, {"duration_ms": 401}, snapshot())

    def test_other_adapters_can_choose_continuous_unit_directions_and_durations(self):
        command = Decision("world_run", None, None, "other-provider", {}, 100, 0, (),
            parameters={"duration_ms": 1753, "direction_world_xy": {"x": .6, "y": .8}})
        self.assertEqual((1753, {"x": 12., "y": 16., "z": 0, "stop_radius_m": .1}),
            commands.execution(command.action, command.parameters, snapshot()))
        for bad in (True, 3001, 1.5, 0):
            with self.assertRaises(ValueError):
                commands.execution("idle", {"duration_ms": bad}, snapshot())

    def test_jev_car_task_chooses_every_action_instead_of_target_macro(self):
        helper = legacy.JevMovementTests()
        def reply(endpoint, key, timeout, payload, **kwargs):
            self.assertNotIn("candidate_automobiles", json.dumps(payload))
            return helper.response(payload, "world_run_d04_3000ms")
        with patch("sa_agent.agents.jev.request_json", side_effect=reply):
            decision = helper.agent().decide(load_task("steal_car"), commands.observation(snapshot()), 0, {}, 100)
        self.assertIsNone(decision.plan)
        self.assertEqual(3000, decision.parameters["duration_ms"])

    @unittest.skipUnless(sys.platform == "win32", "Windows orchestration is mocked")
    def test_slow_model_keeps_walking_and_silent_model_expires(self):
        harness = episodes.MovementEpisodeTests()
        def policy(state, elapsed, timestamp):
            return harness.command(1, 0, timestamp, duration=2400)
        result, sent, supplied, entries = harness.episode(policy, timeout=4, extended=True, delay=1.6)
        self.assertEqual("timeout", result["reason"])
        self.assertGreater(result["final_state"]["player"]["position"]["x"], 8)
        self.assertEqual(0, result["navigation_control_ticks"])
        self.assertTrue(any(s["current_command"] for s in supplied))
        leases = [e for e in entries if e["source"] == "authorized_command_lease"]
        self.assertGreater(len(leases), result["applied_actions"])
        self.assertTrue(all(b["at"] <= a["at"]+a["duration_ms"]/1000 for a,b in zip(sent, sent[1:])))
        self.assertTrue(all(e["elapsed_seconds"]+e["duration_ms"]/1000 <= e["authorization_end_seconds"]+1e-9 for e in leases))
        requested = False
        def one(state, elapsed, timestamp):
            nonlocal requested
            if requested:
                return None
            requested = True
            return harness.command(1, 0, timestamp, duration=1200)
        result, sent, _, entries = harness.episode(one, timeout=3, extended=True)
        self.assertLessEqual(result["final_state"]["player"]["position"]["x"], 4.800001)
        self.assertEqual(1, result["applied_actions"])
        self.assertTrue(all(e["authorization_end_seconds"] <= 1.250001 for e in entries if e["source"] == "authorized_command_lease"))

    @unittest.skipUnless(sys.platform == "win32", "Windows orchestration is mocked")
    def test_adapter_prompt_mutations_cannot_change_task_clock_or_goal(self):
        def mutate(request):
            request[0]["timeout_seconds"] = 0
            request[3]["goal"]["x"] = 0
        result, _, _, _ = episodes.MovementEpisodeTests().episode(
            lambda *args: None, timeout=2, extended=True, mutate_request=mutate)
        self.assertEqual("timeout", result["reason"])
        self.assertGreaterEqual(result["elapsed_seconds"], 2)
        self.assertEqual(8, result["task_progress"]["goal"]["x"])

    @unittest.skipUnless(sys.platform == "win32", "Windows orchestration is mocked")
    def test_current_car_task_cannot_instantiate_shared_controller(self):
        task = load_task("steal_car")
        task["timeout_seconds"] = .5
        harness = episodes.MovementEpisodeTests()
        result, sent, _, entries = harness.episode(lambda state, elapsed, timestamp:
            Decision("enter_exit", None, None, "other-provider", {}, timestamp, 0, (),
                parameters={"duration_ms": 400}), extended=True, task_override=task)
        self.assertEqual("timeout", result["reason"])
        self.assertEqual(0, result["navigation_control_ticks"])
        self.assertEqual(result["applied_actions"], len(sent))  # One lease per entry pulse.
