"""Episode orchestration: independent decision, monitor and recording loops."""

from dataclasses import asdict
import copy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import queue
import threading
import time
import uuid

from .actions import available_actions
from .agents import create_agent
from .game import BridgeUnavailable, ControlBridge, GameClient, kernel
from .recording import VideoRecorder
from .tasks import TaskEvaluator, preconditions
from .windows import GameWindow
from .navigation import CarAcquisition
from .provenance import make_manifest
from . import movement, commands
from .scoring import fixed_window


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    def finite(data):
        if isinstance(data, float) and not math.isfinite(data):
            return None
        if isinstance(data, dict):
            return {key: finite(item) for key, item in data.items()}
        if isinstance(data, (list, tuple)):
            return [finite(item) for item in data]
        return data
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(finite(value), indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


class DecisionWorker:
    """One in-flight API call; the task deadline and recorder never wait on it."""
    def __init__(self, agent):
        self.agent = agent
        self.requests, self.results = queue.Queue(maxsize=1), queue.Queue()
        self.stopping, self.busy = threading.Event(), threading.Event()
        self.thread = threading.Thread(target=self._loop, name="agent-decisions", daemon=True)
        self.thread.start()

    def _loop(self):
        while not self.stopping.is_set():
            request = self.requests.get()
            if request is None:
                return
            try:
                result = (self.agent.decide(*request), None)
            except Exception as error:
                result = (None, f"{type(error).__name__}: {error}")
            if not self.stopping.is_set():
                self.results.put(result)
            self.busy.clear()

    def submit(self, request):
        if self.busy.is_set() or self.stopping.is_set():
            return False
        self.busy.set()
        self.requests.put_nowait(request)
        return True

    def stop(self):
        self.stopping.set()
        try:
            self.requests.put_nowait(None)
        except queue.Full:
            pass
        # An in-flight request may finish, but can never apply an input or change
        # the result after the main thread has closed the control lease.
        self.thread.join(timeout=0.1)


def ready_state(client, window, config):
    deadline = time.monotonic() + config["pause_grace_seconds"]
    last_error = "Resume gameplay before starting a task"
    while time.monotonic() < deadline:
        try:
            state = client.read()
            if (window.foreground() and state.get("player") and state.get("status") == "playing" and
                max(state["sample_age_ms"], state["world"]["sample_age_ms"]) <= config["telemetry_max_age_ms"]):
                return state
        except BridgeUnavailable as error:
            last_error = str(error)
        time.sleep(0.1)
    raise RuntimeError(last_error)


def navigation_ready(state, config):
    nav = state.get("navigation")
    return bool(nav and nav["world_goals_ready"] and
                nav["sample_age_ms"] <= config["telemetry_max_age_ms"])


def record_success_tail(client, window, recorder, config, directory, task_finish, process_id):
    """Observe the aftermath without reevaluating the goal or sending any inputs."""
    seconds = config["recording"].get("post_success_seconds", 15)
    tail = {"requested_seconds": seconds, "recorded_seconds": 0.0,
            "status": "disabled" if not seconds else "recording",
            "started_at_utc": utc_now(), "final_state": None}
    if not seconds:
        tail["finished_at_utc"] = utc_now()
        return tail
    print(f"Task finished; recording {seconds:g} more seconds with agent controls released.", flush=True)
    invalid_since = None
    seen = None
    deadline = task_finish + seconds
    try:
        with (directory / "post_success_observations.jsonl").open("w", encoding="utf-8") as observations:
            while time.monotonic() < deadline:
                now = time.monotonic()
                if recorder.error:
                    tail.update(status="interrupted", reason="recording_error")
                    break
                valid = False
                try:
                    snapshot = client.read()
                    valid = (snapshot.get("live") and snapshot.get("player") and
                        snapshot["process_id"] == process_id and window.foreground() and
                        snapshot["status"] == "playing" and max(snapshot["sample_age_ms"],
                        snapshot["world"]["sample_age_ms"]) <= config["game"]["telemetry_max_age_ms"])
                    if valid:
                        tail["final_state"] = snapshot
                        if snapshot["sample_count"] != seen:
                            observations.write(json.dumps({"seconds_after_success": now-task_finish,
                                "state": snapshot}, allow_nan=False)+"\n")
                            seen = snapshot["sample_count"]
                except BridgeUnavailable:
                    pass
                if valid:
                    invalid_since = None
                else:
                    invalid_since = invalid_since if invalid_since is not None else now
                    if now - invalid_since >= config["game"]["connection_grace_seconds"]:
                        tail.update(status="interrupted", reason="game_paused_not_foreground_or_telemetry_lost")
                        break
                time.sleep(min(0.05, max(0, deadline-time.monotonic())))
            else:
                tail["status"] = "completed"
    except KeyboardInterrupt:
        tail.update(status="cancelled", reason="cancelled_by_user")
    except Exception as error:
        tail.update(status="interrupted", reason=f"{type(error).__name__}: {error}")
    tail["recorded_seconds"] = max(0, time.monotonic()-task_finish)
    tail["finished_at_utc"] = utc_now()
    return tail


def run_task(task, config, output_root):
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    directory = Path(output_root).resolve() / task["id"] / run_id
    directory.mkdir(parents=True, exist_ok=False)
    result = {"schema_version": 1, "manifest": "manifest.json",
              "run_id": run_id, "task_id": task["id"], "task_version": task["version"],
              "agent": config["agent"]["name"], "requested_model": config["agent"]["model"],
              "status": "failed", "reason": "setup_incomplete", "created_at_utc": utc_now(),
              "started_at_utc": None, "finished_at_utc": None, "elapsed_seconds": 0.0,
              "decision_target_hz": config["agent"]["decision_hz"], "decision_count": 0,
              "applied_actions": 0, "stale_decisions_dropped": 0, "models_used": [],
              "accepted_target_selections": 0, "navigation_control_ticks": 0,
              "video": None, "final_state": None, "task_progress": {}, "reset": None,
              "post_success_recording": {"status": "not_applicable",
                  "requested_seconds": config["recording"].get("post_success_seconds", 15),
                  "recorded_seconds": 0.0}}
    write_json(directory / "task.json", task)
    write_json(directory / "config.json", config)  # API key is only an environment variable.
    worker = recorder = controls = None
    agent_actions = commands.uses_agent_actions(task)
    navigator = CarAcquisition() if task["success"]["type"] == "enter_car_as_driver" and not agent_actions else None
    bounded_movement = movement.uses_bounded_movement(task)
    result["policy_mode"] = ("agent_actions" if agent_actions else "bounded_movement" if bounded_movement else
                            "target_selection_with_road_controller" if navigator else "primitive_actions")
    if bounded_movement or agent_actions:
        interface = commands if agent_actions else movement
        result.update(action_interface=interface.INTERFACE, executor_version=interface.EXECUTOR_VERSION,
                      invalid_commands_dropped=0)
    if agent_actions:
        result["native_input_leases"] = 0
    active_command = None
    task_start = task_finish = None
    state = None
    resetting = False
    try:
        write_json(directory / "manifest.json", make_manifest(task, config, result["policy_mode"]))
        agent_config = {**config["agent"], "action_duration_ms": config["game"]["action_duration_ms"]}
        agent = create_agent(agent_config)
        client = GameClient()
        if config.get("reset", {}).get("mode", "none") == "new_game":
            from .lifecycle import ensure_game_running, reset_new_game
            resetting = True
            print(f"Preparing a fresh New Game before {task['id']}; task clock has not started.", flush=True)
            process_info = ensure_game_running(config["reset"])
            controls = ControlBridge().__enter__()
            result["reset"], state, window = reset_new_game(config, controls, directory, process_info)
            resetting = False
            # Auto-installation may have replaced the ASI before launch.
            write_json(directory / "manifest.json", make_manifest(task, config, result["policy_mode"]))
        seed = client.read()
        window = GameWindow.find(seed["process_id"])
        print(f"Task: {task['title']}\nSetup: {task['setup']}\nOutput: {directory}", flush=True)
        print(f"Starting in {config['game']['startup_countdown_seconds']} seconds; keep GTA foreground and unpaused.", flush=True)
        time.sleep(config["game"]["startup_countdown_seconds"])
        window.activate()
        state = ready_state(client, window, config["game"])
        if (navigator or bounded_movement or agent_actions) and not navigation_ready(state, config["game"]):
            raise RuntimeError("Fresh navigation data and world-input support are required. Build/install the current ASI and restart GTA.")
        profile = state["world"]
        if not profile["control_ready"]:
            raise RuntimeError("The ASI input hook is unavailable")
        if ((profile["render_width"], profile["render_height"], profile["fps_cap"]) !=
            (config["game"]["width"], config["game"]["height"], config["game"]["fps_cap"])):
            raise RuntimeError("Game render profile differs from benchmark config; install the INI and restart GTA. Use a resolution supported by your video modes.")
        missing = preconditions(task, state)
        if missing:
            result["reason"] = "preconditions_failed"
            result["precondition_failures"] = missing
            return result, directory
        recorder = VideoRecorder(window, config["recording"], directory)
        recorder.start()
        # Refresh staging after the recorder has acquired its first frame.
        state = ready_state(client, window, config["game"])
        missing = preconditions(task, state)
        if missing:
            result["reason"], result["precondition_failures"] = "preconditions_failed", missing
            return result, directory
        write_json(directory / "initial_state.json", state)
        evaluator = TaskEvaluator(task, state)
        if controls is None:
            controls = ControlBridge().__enter__()
        worker = DecisionWorker(agent)
        task_start = time.monotonic()
        if fixed_window(task):
            evaluator.window_score.begin(kernel.GetTickCount64())
        result["started_at_utc"] = utc_now()
        next_decision = task_start
        invalid_since = paused_since = None
        first_action_at = None
        any_ack = False
        sent_requests = set()
        errors = 0
        seen_counter = None
        models = set()
        last_progress = {}
        next_control = 0
        with (directory / "observations.jsonl").open("w", encoding="utf-8") as observations, \
             (directory / "actions.jsonl").open("w", encoding="utf-8") as actions:
            while True:
                now = time.monotonic()
                elapsed = now - task_start
                if elapsed >= task["timeout_seconds"]:
                    controls.release()
                    active_command = None
                    if fixed_window(task) and invalid_since is None and paused_since is None:
                        # Drain late-published death events using their engine timestamps.
                        # Cash from a sample after the deadline is explicitly excluded.
                        final_sample = client.read()
                        fresh = (final_sample.get("live") and final_sample.get("player") and
                            final_sample["process_id"] == seed["process_id"] and window.foreground() and
                            final_sample.get("status") == "playing" and max(final_sample["sample_age_ms"],
                            (final_sample.get("actors") or {}).get("sample_age_ms", float("inf"))) <= config["game"]["telemetry_max_age_ms"])
                        failure = evaluator.window_score.update(final_sample) if fresh else "scoring_telemetry_unavailable"
                        result["status"] = "failed" if failure else "completed"
                        result["reason"] = failure or "window_completed"
                        result["task_progress"] = evaluator.window_score.report(completed=not failure)
                    else:
                        result["reason"] = "scoring_window_interrupted" if fixed_window(task) else "timeout"
                    break
                if recorder.error:
                    result["reason"] = "recording_error"
                    break
                try:
                    state = client.read()
                    valid = (state.get("live") and state.get("player") and window.foreground() and
                             state["process_id"] == seed["process_id"] and
                             max(state["sample_age_ms"], state["world"]["sample_age_ms"]) <= config["game"]["telemetry_max_age_ms"])
                    if navigator or bounded_movement or agent_actions:
                        valid = valid and navigation_ready(state, config["game"])
                    if fixed_window(task):
                        actors = state.get("actors") or {}
                        valid = valid and actors.get("sample_age_ms", float("inf")) <= config["game"]["telemetry_max_age_ms"]
                except BridgeUnavailable:
                    valid = False
                if not valid:
                    controls.release()
                    active_command = None
                    evaluator.suspend()
                    invalid_since = invalid_since if invalid_since is not None else now
                    if now - invalid_since >= config["game"]["connection_grace_seconds"]:
                        result["reason"] = "game_not_foreground_or_telemetry_lost"
                        break
                    time.sleep(0.05)
                    continue
                invalid_since = None
                if state["sample_count"] != seen_counter:
                    observations.write(json.dumps({"elapsed_seconds": elapsed, "state": state}, allow_nan=False) + "\n")
                    seen_counter = state["sample_count"]
                if state["status"] == "paused":
                    controls.release()
                    active_command = None
                    evaluator.suspend()
                    paused_since = paused_since if paused_since is not None else now
                    if now - paused_since >= config["game"]["pause_grace_seconds"]:
                        result["reason"] = "game_paused"
                        break
                    time.sleep(0.05)
                    continue
                paused_since = None
                verdict = evaluator.evaluate(state, elapsed)
                last_progress = verdict.progress
                if navigator:
                    last_progress["navigation_controller"] = navigator.progress(state, elapsed)
                result["task_progress"] = last_progress
                if verdict.failure or verdict.success:
                    result["status"] = "success" if verdict.success else "failed"
                    result["reason"] = "goal_reached" if verdict.success else verdict.failure
                    break
                if first_action_at is not None:
                    any_ack = any_ack or state["world"]["last_applied_request"] in sent_requests
                    if not any_ack and now - first_action_at > 3:
                        result["reason"] = "controls_not_acknowledged"
                        break
                while True:
                    try:
                        decision, error = worker.results.get_nowait()
                    except queue.Empty:
                        break
                    if error:
                        errors += 1
                        controls.release()
                        active_command = None
                        actions.write(json.dumps({"elapsed_seconds": elapsed, "error": error}) + "\n")
                        if errors >= config["agent"]["max_consecutive_errors"]:
                            result["reason"], result["agent_error"] = "agent_error", error
                            break
                        continue
                    errors = 0
                    result["decision_count"] += 1
                    models.add(decision.model)
                    result["models_used"] = sorted(models)
                    age = time.monotonic() - decision.observation_time
                    permitted = available_actions(task, state)
                    applied = age <= config["agent"]["max_decision_age_seconds"] and decision.action in permitted
                    entry = {**asdict(decision), "elapsed_seconds": elapsed,
                             "decision_age_seconds": age, "applied": applied}
                    duration, goal = config["game"]["action_duration_ms"], None
                    if (bounded_movement or agent_actions) and applied:
                        try:
                            if decision.plan is not None:
                                raise ValueError("Execution plans are not supported by bounded movement")
                            duration, goal = interface.execution(decision.action, decision.parameters, state)
                            # The final lease cannot extend beyond the scored deadline.
                            remaining_ms = int((task_start+task["timeout_seconds"]-time.monotonic())*1000)
                            if remaining_ms < 1:
                                applied = False
                                entry["drop_reason"] = "task_deadline"
                            else:
                                duration = min(duration, remaining_ms)
                        except ValueError as error:
                            applied = False
                            entry.update(drop_reason="invalid_command", detail=str(error))
                            result["invalid_commands_dropped"] += 1
                    entry["applied"] = applied
                    if navigator:
                        applied = applied and navigator.accept(decision.plan, state, elapsed)
                        entry.update(source="jev_target_selection", applied=applied)
                        if applied:
                            result["accepted_target_selections"] += 1
                    elif applied:
                        if bounded_movement or agent_actions:
                            entry.update(source="agent_action", duration_ms=duration, goal=goal,
                                         executor_version=interface.EXECUTOR_VERSION,
                                         execution_origin=dict(state["player"]["position"]),
                                         execution_sample_count=state["sample_count"])
                        if agent_actions:
                            entry["command_id"] = result["decision_count"]
                            active_command = commands.AuthorizedCommand(decision.action,
                                decision.parameters, goal, time.monotonic(), duration,
                                entry["command_id"], state["player"]["in_vehicle"])
                            # Authorizations never extend beyond the scored deadline.
                            active_command.deadline = min(active_command.deadline,
                                task_start + task["timeout_seconds"])
                        else:
                            entry["request_id"] = controls.send(decision.action, duration, goal=goal)
                            sent_requests.add(entry["request_id"])
                        result["applied_actions"] += 1
                        first_action_at = first_action_at or now
                    if not applied:
                        controls.release()
                        active_command = None
                        if age > config["agent"]["max_decision_age_seconds"]:
                            entry["drop_reason"] = "decision_stale"
                            result["stale_decisions_dropped"] += 1
                        elif "drop_reason" not in entry:
                            entry["drop_reason"] = "target_wait_or_no_longer_eligible" if navigator else "action_no_longer_allowed"
                    actions.write(json.dumps(entry, allow_nan=False) + "\n")
                if result["reason"] == "agent_error":
                    break
                if active_command:
                    lease_now = time.monotonic()
                    if lease_now >= active_command.deadline or state["player"]["in_vehicle"] != active_command.in_vehicle:
                        controls.release()
                        active_command = None
                    else:
                        lease = active_command.lease(lease_now, state["player"]["in_vehicle"])
                        if lease:
                            request_id = controls.send(active_command.action, lease, goal=active_command.goal)
                            sent_requests.add(request_id)
                            result["native_input_leases"] += 1
                            actions.write(json.dumps({"source": "authorized_command_lease",
                                "command_id": active_command.command_id, "request_id": request_id,
                                "action": active_command.action, "goal": active_command.goal,
                                "duration_ms": lease, "elapsed_seconds": lease_now-task_start,
                                "authorization_end_seconds": active_command.deadline-task_start,
                                "applied": True}, allow_nan=False)+"\n")
                if navigator and now >= next_control:
                    intent = navigator.tick(state, elapsed)
                    if intent.action not in available_actions(task, state):
                        raise RuntimeError("Navigation controller proposed an action outside the task action set")
                    request_id = controls.send(intent.action, config["game"]["action_duration_ms"], goal=intent.goal)
                    sent_requests.add(request_id)
                    result["applied_actions"] += 1
                    result["navigation_control_ticks"] += 1
                    first_action_at = first_action_at or now
                    actions.write(json.dumps({"source": "navigation_controller", "elapsed_seconds": elapsed,
                        "action": intent.action, "goal": intent.goal, "reason": intent.reason,
                        "phase": navigator.phase, "target_vehicle_reference": navigator.target,
                        "request_id": request_id, "applied": True}, allow_nan=False)+"\n")
                    last_progress["navigation_controller"] = navigator.progress(state, elapsed)
                    result["task_progress"] = last_progress
                    next_control = now+0.1
                needs_decision = not navigator or (navigator.target is None and
                    bool(last_progress["navigation_controller"]["candidates"]))
                if now >= next_decision and not worker.busy.is_set() and needs_decision:
                    agent_state = (commands.observation(state) if agent_actions else
                                   movement.observation(state) if bounded_movement else state)
                    if agent_actions:
                        agent_state["current_command"] = active_command.describe(now) if active_command else None
                    # Adapters may build/mutate their own prompt data. Their
                    # copies must not alter the runner's task rules or judgment.
                    worker.submit((copy.deepcopy(task), copy.deepcopy(agent_state), elapsed,
                                   copy.deepcopy(last_progress), now))
                    next_decision = now + (2.0 if navigator else 1.0 / config["agent"]["decision_hz"])
                time.sleep(0.05)
    except KeyboardInterrupt:
        result["reason"] = "cancelled_by_user"
    except Exception as error:
        result["reason"] = "reset_failed" if resetting else "runtime_error" if task_start else "setup_error"
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        task_finish = time.monotonic()
        if fixed_window(task) and task_start:
            if result["status"] == "completed":
                task_finish = task_start + 120
            elif result["status"] == "failed" and result["reason"] in {"player_died", "player_arrested"}:
                result["status"] = "incomplete"
            result.update(evaluator.window_score.report(completed=result["status"] == "completed"))
        result["elapsed_seconds"] = task_finish - task_start if task_start else 0.0
        result["finished_at_utc"] = utc_now()
        result["task_status"], result["task_reason"] = result["status"], result["reason"]
        result["final_state"] = state
        result["artifacts_status"] = "finalizing"
        if resetting and (directory / "reset.json").is_file():
            result["reset"] = json.loads((directory / "reset.json").read_text(encoding="utf-8"))
        cleanup_errors = []
        if controls:
            try:
                # Keep the ownership mutex until the video is finalized so a
                # second runner cannot reset GTA during this recording's tail.
                controls.release()
            except Exception as error:
                cleanup_errors.append(f"Control cleanup: {type(error).__name__}: {error}")
        if worker:
            worker.stop()
        # Save the terminal task verdict before the optional aftermath recording.
        # The task time, final state and verdict are frozen at the success frame.
        if result["status"] in {"success", "completed"}:
            result["post_success_recording"]["status"] = "pending"
        try:
            write_json(directory / "result.json", result)
        except OSError as error:
            cleanup_errors.append(f"Result write: {type(error).__name__}: {error}")
        if recorder and result["status"] in {"success", "completed"} and not cleanup_errors:
            result["post_success_recording"] = record_success_tail(
                client, window, recorder, config, directory, task_finish, seed["process_id"])
        elif result["post_success_recording"]["status"] == "pending":
            result["post_success_recording"].update(status="skipped", reason="cleanup_error")
        if recorder:
            try:
                result["video"] = recorder.stop()
            except Exception as error:
                result["video"] = {"path": None, "error": f"{type(error).__name__}: {error}"}
            if result["video"]["error"]:
                result["task_status_before_recording_error"] = result["status"]
                result["status"], result["reason"] = "failed", "recording_error"
            if recorder.started_at is not None and task_start is not None:
                result["video"]["task_start_seconds"] = max(0, task_start-recorder.started_at)
                result["video"]["task_end_seconds"] = max(0, task_finish-recorder.started_at)
        if controls:
            try:
                controls.close()
            except Exception as error:
                cleanup_errors.append(f"Control close: {type(error).__name__}: {error}")
        if cleanup_errors:
            result["status"], result["reason"] = "failed", "cleanup_error"
            result["cleanup_errors"] = cleanup_errors
        result["artifacts_finished_at_utc"] = utc_now()
        result["artifacts_status"] = "failed" if cleanup_errors or (result.get("video") or {}).get("error") else "complete"
        if task_start:
            result["observed_decision_hz"] = result["decision_count"] / max(result["elapsed_seconds"], 0.001)
            if navigator:
                result["observed_navigation_control_hz"] = result["navigation_control_ticks"] / max(result["elapsed_seconds"], 0.001)
        write_json(directory / "result.json", result)
    return result, directory
