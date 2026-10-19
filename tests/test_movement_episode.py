"""Runner integration with an independent collision/lease simulator, never GTA or an API."""

import copy
import json
import queue
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sa_agent.agents.base import Decision
from test_episode import Clock, Window, snapshot

if sys.platform == "win32":
    from sa_agent import runner
    from sa_agent.config import ROOT, load_config
    from sa_agent.tasks import load_task


@unittest.skipUnless(sys.platform == "win32", "Windows bindings; game/model/capture are mocked")
class MovementEpisodeTests(unittest.TestCase):
    def episode(self, policy, timeout=8, wall=False, extended=False, delay=0, task_override=None, mutate=None, mutate_request=None):
        clock = Clock()
        state = snapshot()
        state["player"]["position"] = {"x": 0., "y": 0., "z": 0.}
        state["world"]["nearby_vehicles"] = []
        config = load_config(ROOT / "configs/benchmark.json")
        config["reset"]["mode"] = "none"
        config["recording"]["post_success_seconds"] = 0
        config["game"]["startup_countdown_seconds"] = 0
        task = load_task("walk_to_waypoint")
        task["action_interface"] = "agent_actions_v1" if extended else "bounded_movement_v1"
        task["timeout_seconds"] = timeout
        task["success"].update(position={"x": 8, "y": 0, "z": 0}, radius_m=.6)
        if task_override:
            task = task_override
        if task["success"]["type"] in {"npc_kills", "net_money"}:
            state["player"]["money"] = 100
            state["actors"] = {"kill_events_ready": True, "combat_ready": True,
                "sample_age_ms": 0, "sampled_at_ms": 100000, "latest_event_id": 0, "kill_events": []}
        sent, supplied = [], []
        active = None
        previous = clock.now

        class Controls:
            def __enter__(self):
                return self

            def send(self, action, duration_ms, goal=None):
                nonlocal active
                reference = len(sent) + 1
                sent.append({"action": action, "duration_ms": duration_ms,
                             "goal": goal, "at": clock.now})
                active = {"action": action, "goal": goal, "expires": clock.now+duration_ms/1000}
                state["world"]["last_applied_request"] = reference
                return reference

            def release(self):
                nonlocal active
                active = None

            def close(self):
                self.release()

        def read():
            nonlocal previous
            if active and active["goal"] is not None:
                dt = max(0, min(clock.now, active["expires"]) - previous)
                player, goal = state["player"]["position"], active["goal"]
                dx, dy = goal["x"]-player["x"], goal["y"]-player["y"]
                length = (dx*dx+dy*dy)**.5
                step = min(length, dt*4)
                if length:
                    x, y = player["x"]+dx/length*step, player["y"]+dy/length*step
                    if not (wall and 3 <= x <= 4 and -2 <= y <= 2):
                        player.update(x=x, y=y)
            previous = clock.now
            state["sample_count"] += 1
            state["game_time_ms"] = round((clock.now-100)*1000)
            state["sampled_at_ms"] = round(clock.now*1000)
            if mutate:
                mutate(clock.now-100, state)
            return copy.deepcopy(state)

        class Worker:
            def __init__(self, agent):
                self.pending = None
                self.queue = queue.Queue()
                self.busy = SimpleNamespace(is_set=lambda: self.pending is not None)

            @property
            def results(self):
                if self.pending and clock.now >= self.pending[0]:
                    self.queue.put(self.pending[1])
                    self.pending = None
                return self.queue

            def submit(self, request):
                if mutate_request:
                    mutate_request(request)
                supplied.append(copy.deepcopy(request[1]))
                decision = policy(request[1], request[2], request[4])
                if decision is not None:
                    self.pending = (clock.now+delay, (decision, None))
                return True

            def stop(self):
                pass

        class Recorder:
            error = None
            started_at = None

            def __init__(self, *args):
                pass

            def start(self):
                pass

            def stop(self):
                return {"error": None}

        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(runner, "time", clock), \
             patch.object(runner, "GameClient", return_value=SimpleNamespace(read=read)), \
             patch.object(runner.GameWindow, "find", return_value=Window()), \
             patch.object(runner, "ControlBridge", Controls), \
             patch.object(runner, "VideoRecorder", Recorder), \
             patch.object(runner, "DecisionWorker", Worker), \
             patch.object(runner, "CarAcquisition", side_effect=AssertionError("Hidden navigation controller")), \
             patch.object(runner, "create_agent", return_value=object()), \
             patch.object(runner, "make_manifest", return_value={}):
            with patch.object(runner.kernel, "GetTickCount64", side_effect=lambda: round(clock.now*1000)):
                result, directory = runner.run_task(task, config, temporary)
            entries = [json.loads(line) for line in (directory / "actions.jsonl").read_text().splitlines()]
        return result, sent, supplied, entries

    def command(self, x, y, timestamp, duration=600):
        return Decision("world_run", None, None, "fixture-agent", {}, timestamp, 0, (),
            parameters={"direction_world_xy": {"x": x, "y": y}, "duration_ms": duration})

    def test_complete_agent_can_choose_a_detour_and_every_input_is_attributable(self):
        # The detour is supplied by this test agent, outside the benchmark executor.
        points = [(2, 3), (6, 3), (8, 0)]
        def policy(state, elapsed, timestamp):
            player = state["player"]["position"]
            while len(points) > 1 and (points[0][0]-player["x"])**2 + (points[0][1]-player["y"])**2 < .5**2:
                points.pop(0)
            dx, dy = points[0][0]-player["x"], points[0][1]-player["y"]
            distance = (dx*dx+dy*dy)**.5
            if distance < .5:
                return Decision("idle", None, None, "fixture-agent", {}, timestamp, 0, (),
                                parameters={"duration_ms": 600})
            return self.command(dx/distance, dy/distance, timestamp)
        result, sent, supplied, entries = self.episode(policy, wall=True)
        self.assertEqual("success", result["status"])
        self.assertEqual(0, result["navigation_control_ticks"])
        self.assertEqual(len(sent), result["applied_actions"])
        self.assertEqual(len(sent), sum(e["applied"] for e in entries))
        self.assertTrue(all(e["source"] == "agent_action" for e in entries))
        self.assertTrue(all(s["observation_interface"] == "bounded_movement_v1" for s in supplied))
        self.assertTrue(any(s["player"]["position"]["y"] > 2 for s in supplied))

    def test_blocked_agent_never_receives_an_automatic_detour(self):
        result, sent, _, _ = self.episode(lambda state, elapsed, timestamp: self.command(1, 0, timestamp),
                                         timeout=4, wall=True)
        self.assertEqual("timeout", result["reason"])
        self.assertLess(result["final_state"]["player"]["position"]["x"], 3)
        self.assertEqual(0, result["final_state"]["player"]["position"]["y"])
        self.assertTrue(all(s["goal"]["y"] == 0 for s in sent))

    def test_one_command_expires_without_automatic_renewal(self):
        requested = False
        def policy(state, elapsed, timestamp):
            nonlocal requested
            if requested:
                return None  # Model provides no further actions.
            requested = True
            return self.command(1, 0, timestamp, duration=200)
        result, sent, _, _ = self.episode(policy, timeout=2)
        self.assertEqual("timeout", result["reason"])
        self.assertEqual(1, len(sent))
        self.assertLessEqual(result["final_state"]["player"]["position"]["x"], .800001)

    def test_stale_and_invalid_commands_are_dropped_without_movement(self):
        for stale in (False, True):
            def policy(state, elapsed, timestamp):
                return self.command(1, 0, timestamp-3 if stale else timestamp,
                                    duration=600 if stale else 10000)
            result, sent, _, entries = self.episode(policy, timeout=1)
            self.assertEqual([], sent)
            self.assertEqual(0, result["applied_actions"])
            self.assertEqual("timeout", result["reason"])
            reason = "decision_stale" if stale else "invalid_command"
            self.assertTrue(all(e["drop_reason"] == reason for e in entries))
            self.assertGreater(len(entries), 0)

    def test_final_command_is_shortened_to_the_task_deadline(self):
        result, sent, _, _ = self.episode(
            lambda state, elapsed, timestamp: self.command(1, 0, timestamp), timeout=.3)
        self.assertEqual("timeout", result["reason"])
        self.assertTrue(sent)
        for command in sent:
            self.assertLessEqual(command["at"]+command["duration_ms"]/1000, 100.300001)
