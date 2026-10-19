import copy
import sys
import unittest
from sa_agent.scoring import WindowScore
from sa_agent.tasks import TaskEvaluator, load_task, validate_task
import test_movement_episode as episodes
from test_movement import snapshot


def initial():
    state = snapshot()
    state["player"]["money"] = 100
    state["sampled_at_ms"] = 1000
    state["actors"] = {"sampled_at_ms": 1000, "latest_event_id": 5,
                       "kill_events_ready": True, "combat_ready": True, "kill_events": []}
    return state


class ScoreTests(unittest.TestCase):
    def test_kills_count_confirmed_new_events_once_even_after_unload(self):
        state = initial()
        score = WindowScore(load_task("kill_npc"), state)
        score.begin(1000)
        state["actors"].update(latest_event_id=7, kill_events=[
            {"event_id": 6, "victim_reference": 257, "player_attributed": True, "occurred_at_ms": 999},
            {"event_id": 7, "victim_reference": 513, "player_attributed": True, "occurred_at_ms": 120999}])
        self.assertIsNone(score.update(state))
        self.assertIsNone(score.update(state))
        self.assertEqual(1, score.report()["score"])
        state["actors"].update(latest_event_id=8, kill_events=[
            {"event_id": 8, "victim_reference": 769, "player_attributed": True, "occurred_at_ms": 121000}])
        score.update(state)
        self.assertEqual(1, score.report()["score"])

    def test_missing_event_evidence_fails_instead_of_silently_undercounting(self):
        state = initial()
        score = WindowScore(load_task("kill_npc"), state)
        state["actors"].update(latest_event_id=7, kill_events=[{"event_id": 7}])
        self.assertEqual("kill_event_evidence_lost", score.update(state))

    def test_other_actor_death_or_disappearing_ped_never_earns_a_kill(self):
        state = initial()
        score = WindowScore(load_task("kill_npc"), state)
        state["actors"]["nearby_peds"] = []
        self.assertIsNone(score.update(state))
        self.assertEqual(0, score.report()["score"])
        state["actors"].update(latest_event_id=6, kill_events=[{
            "event_id": 6, "victim_reference": 257, "player_attributed": False, "occurred_at_ms": 2000}])
        self.assertIsNone(score.update(state))
        self.assertEqual(0, score.report()["score"])

    def test_cash_is_net_balance_and_excludes_post_deadline_payouts(self):
        state = initial()
        score = WindowScore(load_task("earn_money"), state)
        state["player"]["money"], state["sampled_at_ms"] = 75, 120999
        score.update(state)
        self.assertEqual(-25, score.report()["score"])
        state["player"]["money"], state["sampled_at_ms"] = 1000, 121001
        score.update(state)
        self.assertEqual(-25, score.report(completed=True)["score"])
        self.assertTrue(score.report(completed=True)["score_complete"])

    def test_death_and_arrest_preserve_partial_score_without_early_success(self):
        for failure in ("player_died", "player_arrested"):
            state = initial()
            evaluator = TaskEvaluator(load_task("earn_money"), state)
            state["sample_count"] += 1
            state["sampled_at_ms"], state["player"]["money"] = 2000, 140
            verdict = evaluator.evaluate(state, 1)
            self.assertFalse(verdict.success)
            state["sample_count"] += 1
            state["player"]["health"] = 0 if failure == "player_died" else 100
            state["world"]["player_state"] = 1 if failure == "player_died" else 2
            verdict = evaluator.evaluate(state, 2)
            self.assertEqual(failure, verdict.failure)
            self.assertEqual(40, verdict.progress["score"])
            self.assertFalse(verdict.progress["score_complete"])

    def test_scored_tasks_cannot_be_shortened_or_disable_death(self):
        for changes in ({"timeout_seconds": 119}, {"fail_on_death": False}, {"action_interface": "bounded_movement_v1"}):
            with self.assertRaises(ValueError):
                validate_task({**load_task("kill_npc"), **changes})

    @unittest.skipUnless(sys.platform == "win32", "Windows orchestration is mocked")
    def test_runner_completes_exact_window_and_keeps_partial_death_separate(self):
        def mutate(elapsed, state):
            state["player"]["money"] = 100 if elapsed < .4 else 125 if elapsed < 120 else 9000
        harness = episodes.MovementEpisodeTests()
        result, _, _, _ = harness.episode(lambda *args: None, extended=True,
            task_override=load_task("earn_money"), mutate=mutate)
        self.assertEqual("completed", result["status"])
        self.assertEqual(120, result["elapsed_seconds"])
        self.assertEqual(25, result["score"])
        self.assertTrue(result["score_complete"])
        def dies(elapsed, state):
            state["player"]["money"] = 100 if elapsed < .4 else 130
            if elapsed > 2:
                state["player"]["health"] = 0
        result, _, _, _ = harness.episode(lambda *args: None, extended=True,
            task_override=load_task("earn_money"), mutate=dies)
        self.assertEqual("incomplete", result["status"])
        self.assertEqual(30, result["score"])
        self.assertFalse(result["score_complete"])
