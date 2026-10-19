"""Mocked Windows orchestration tests; no game, capture device or model calls."""

import copy
from pathlib import Path
import queue
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

if sys.platform == "win32":
    from sa_agent import lifecycle, runner
    from sa_agent.config import ROOT, load_config
    from sa_agent.tasks import Verdict, load_task


class Clock:
    def __init__(self):
        self.now = 100.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def snapshot():
    return {"process_id": 123, "live": True, "status": "playing", "sample_age_ms": 0,
        "game_time_ms": 100,
        "sample_count": 1, "player": {"position": {"x": 2235, "y": -1265, "z": 24},
            "in_vehicle": False, "interior": 0, "health": 100, "wanted_level": 0, "speed_mps": 0},
        "vehicle": None, "world": {"sample_age_ms": 0, "control_ready": True,
            "render_width": 1280, "render_height": 720, "fps_cap": 30,
            "player_state": 0, "last_applied_request": 0,
            "camera_forward_xy": {"x": 0, "y": 1},
            "nearby_vehicles": [{"reference": 257, "model_id": 481, "distance_m": 3}]},
        "navigation": {"world_goals_ready": True, "sample_age_ms": 0,
                       "vehicles": [], "nodes": [], "rays": []}}


class Window:
    def activate(self):
        pass

    def foreground(self):
        return True


@unittest.skipUnless(sys.platform == "win32", "Windows bindings; all operations are mocked")
class EpisodeTests(unittest.TestCase):
    def config(self):
        return load_config(ROOT / "configs/benchmark.json")

    def test_success_time_stays_frozen_while_recording_continues(self):
        clock, events = Clock(), []
        config = self.config()
        config["reset"]["mode"] = "none"
        config["game"]["startup_countdown_seconds"] = 0
        client = SimpleNamespace(read=lambda: copy.deepcopy(snapshot()))

        class Controls:
            def __enter__(self):
                return self

            def release(self):
                events.append("release")

            def close(self):
                events.append("close")

        class Recorder:
            error = None

            def __init__(self, window, video_config, directory):
                self.started_at = clock.monotonic()

            def start(self):
                pass

            def stop(self):
                events.append("video_stop")
                return {"error": None, "video_duration_seconds": clock.monotonic()-self.started_at}

        worker = SimpleNamespace(results=queue.Queue(), busy=SimpleNamespace(is_set=lambda: True),
                                 stop=lambda: events.append("worker_stop"))
        evaluator = SimpleNamespace(evaluate=lambda state, elapsed: Verdict(success=elapsed >= .2),
                                    suspend=lambda: None)
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(runner, "time", clock), \
             patch.object(runner, "GameClient", return_value=client), \
             patch.object(runner.GameWindow, "find", return_value=Window()), \
             patch.object(runner, "ControlBridge", Controls), \
             patch.object(runner, "VideoRecorder", Recorder), \
             patch.object(runner, "DecisionWorker", return_value=worker), \
             patch.object(runner, "TaskEvaluator", return_value=evaluator), \
             patch.object(runner, "create_agent", return_value=object()), \
             patch.object(runner, "make_manifest", return_value={"schema_version": 1}):
            result, _ = runner.run_task(load_task("walk_to_waypoint"), config, temporary)
        self.assertEqual("success", result["task_status"])
        self.assertEqual("success", result["status"])
        self.assertLess(result["elapsed_seconds"], 1)
        self.assertEqual("completed", result["post_success_recording"]["status"])
        self.assertAlmostEqual(15, result["post_success_recording"]["recorded_seconds"], places=5)
        self.assertGreater(result["video"]["video_duration_seconds"], 15)
        self.assertLess(result["video"]["task_end_seconds"], 1)
        self.assertLess(events.index("release"), events.index("video_stop"))
        self.assertLess(events.index("worker_stop"), events.index("video_stop"))
        self.assertLess(events.index("video_stop"), events.index("close"))

    def test_interrupted_aftermath_reports_reason_without_reevaluating_task(self):
        clock = Clock()
        with tempfile.TemporaryDirectory() as temporary, patch.object(runner, "time", clock):
            tail = runner.record_success_tail(SimpleNamespace(read=lambda: snapshot()),
                SimpleNamespace(foreground=lambda: False), SimpleNamespace(error=None),
                self.config(), Path(temporary), clock.monotonic(), 123)
        self.assertEqual("interrupted", tail["status"])
        self.assertIn("not_foreground", tail["reason"])
        self.assertLess(tail["recorded_seconds"], 15)

    def reset_case(self, new_generation=True):
        clock, actions = Clock(), []
        config = self.config()
        config["reset"].update(timeout_seconds=10, settle_seconds=.4)
        requested = acknowledged = False

        class Bridge:
            def send(self, action, reset, request_id=None):
                nonlocal requested, acknowledged
                actions.append(action)
                requested = requested or action == 1
                acknowledged = acknowledged or action == 3
                return 42

            def close(self):
                pass

        def status():
            return {"process_id": 123, "request_id": 42 if requested else 0,
                "owner_pid": lifecycle.os.getpid() if requested else 0,
                "session_generation": 5 if requested and new_generation else 4,
                "phase": "ready" if acknowledged else "preparing_intro" if requested else "idle",
                "controllable_stable": True, "player_controllable": True,
                "sample_age_ms": 0, "error": None, "cutscenes_skipped": 2}

        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(lifecycle, "time", clock), \
             patch.object(lifecycle, "read_status", side_effect=status), \
             patch.object(lifecycle, "process_alive", return_value=True), \
             patch.object(lifecycle, "ResetBridge", return_value=Bridge()), \
             patch.object(lifecycle.GameWindow, "find", return_value=Window()), \
             patch.object(lifecycle, "GameClient", return_value=SimpleNamespace(read=lambda: snapshot())):
            call = lambda: lifecycle.reset_new_game(config, SimpleNamespace(release=lambda: None),
                temporary, {"process_id": 123, "launched_game": False})
            if new_generation:
                metadata, _, _ = call()
                self.assertEqual("ready", metadata["status"])
                self.assertIn(3, actions)  # Host completion after fresh start validation.
                self.assertNotIn(2, actions)
            else:
                with self.assertRaisesRegex(RuntimeError, "timed out"):
                    call()
                self.assertNotIn(3, actions)
                self.assertIn(2, actions)

    def test_reset_requires_host_completion_acknowledgement(self):
        self.reset_case(new_generation=True)

    def test_old_session_cannot_pass_starting_state_checks(self):
        self.reset_case(new_generation=False)
