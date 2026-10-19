"""Fixed-window scores from engine evidence, independent of any model adapter."""

KINDS = {"npc_kills", "net_money"}


def fixed_window(task):
    return task["success"]["type"] in KINDS


class WindowScore:
    def __init__(self, task, initial):
        self.kind = task["success"]["type"]
        self.start_cash = self.end_cash = initial["player"]["money"]
        self.last_event = initial["actors"]["latest_event_id"]
        self.kills = []
        self.start_ms = initial["actors"]["sampled_at_ms"]
        self.end_ms = self.start_ms + 120000
        self.cash_sample_ms = initial.get("sampled_at_ms", self.start_ms)

    def begin(self, tick_ms):
        self.start_ms, self.end_ms = tick_ms, tick_ms + 120000

    def update(self, state):
        actors = state.get("actors")
        if not actors or not actors.get("kill_events_ready"):
            return "scoring_telemetry_unavailable"
        if self.kind == "npc_kills":
            events = [e for e in actors["kill_events"] if e["event_id"] > self.last_event]
            if actors["latest_event_id"] < self.last_event:
                return "kill_event_counter_reset"
            for event in events:
                if event["event_id"] != self.last_event + 1:
                    return "kill_event_evidence_lost"
                self.last_event = event["event_id"]
                if self.start_ms <= event["occurred_at_ms"] < self.end_ms and event["player_attributed"]:
                    self.kills.append(dict(event))
            if self.last_event != actors["latest_event_id"]:
                return "kill_event_evidence_lost"
        sampled = state.get("sampled_at_ms", 0)
        if self.start_ms <= sampled < self.end_ms and sampled >= self.cash_sample_ms:
            self.end_cash, self.cash_sample_ms = state["player"]["money"], sampled
        return None

    def report(self, completed=False):
        score = len(self.kills) if self.kind == "npc_kills" else self.end_cash-self.start_cash
        return {"score": score, "score_unit": "kills" if self.kind == "npc_kills" else "game_dollars",
            "score_complete": completed, "window_seconds": 120,
            "window_start_tick_ms": self.start_ms, "window_end_tick_ms": self.end_ms,
            "starting_cash": self.start_cash, "ending_cash": self.end_cash,
            "cash_sample_tick_ms": self.cash_sample_ms, "confirmed_kill_events": self.kills}
