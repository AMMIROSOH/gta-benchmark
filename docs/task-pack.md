# Task pack and fixed-window scoring

GTA Benchmark (`gta-benchmark`) replaces `park_and_exit` with `kill_npc`
and `lose_wanted` with `earn_money`. `steal_car`, `walk_to_waypoint` and
`drive_100m` retain their existing goals.

The five current JSON definitions use [agent-owned actions](agent-actions.md).
The old parking/wanted tasks remain loadable from `tasks/legacy/`. Their results
and the assisted steal-car v3 baseline retain their original meaning.

## Shared two-minute scoring window

Both new tasks measure how much an agent achieves in exactly **120 seconds**.
A completed window produces a numeric score; reaching a particular count or
cash amount never ends the task early. Expiry is normal completion for these
score benchmarks. Goal-task timeouts still represent failure.

Preparation, scenario staging and recorder startup finish before the task clock
starts. Model latency and temporary pauses consume the same wall-time budget
as in the current runner. Only events within the scored window count. Freeze
the score at the deadline; aftermath footage and artifact finalization add
neither task time nor score.

Death or arrest ends the attempt early. Retain the partial score and elapsed
time for diagnosis, but label it incomplete and report it separately from
completed 120-second attempts. Infrastructure failures must also be identified
separately. Do not present a shortened attempt as a completed two-minute score.

Each comparison needs the same documented starting location, health, armor,
weapons/ammunition, cash, wanted level and scenario preparation. NPC and traffic
availability remain stochastic unless a future fixture controls them. No
specific fixture or new automatic staging support is implemented here.

## `kill_npc`: maximize NPC kills

Replaces `park_and_exit` in the intended task pack.

- **Objective:** Kill as many NPCs as possible within two minutes.
- **Primary score:** The number of distinct NPC deaths attributable to the
  player's actions during the 120-second window; higher is better.
- **Counting:** Count each NPC once, at the confirmed death event. Damage alone,
  bodies already dead at the start and deaths caused solely by other actors do
  not count. A disappearing or unloaded NPC is not proof of a kill.
- **Evidence needed:** Host-observed kill attribution and stable event/entity
  identity, including events whose victims later leave the nearby entity set.
  Model claims and local video frames are not scoring inputs.

The native bridge observes `CEventHandler::RegisterKill` at SA 1.0-US address
`0x4B9340`, preserving the original game call. It accepts the player ped or the
player's current vehicle as the source, excludes the player as victim, and
deduplicates a victim lifetime by pool slot/generation. This is an engine death
registration, rather than an inference from damage or disappearance.
Victim deduplication resets on a new game-session generation, because New Game
can reuse the same pool references. Event IDs remain monotonic for the process.
The ABI retains 128 events with monotonic event IDs and Windows tick timestamps.
The scorer ignores pre-window and post-window events and fails explicitly if
event evidence is lost or the counter resets. Nearby NPC observations are
independent of this event ring. See the
[inspected engine routine](https://github.com/gta-reversed/gta-reversed/blob/master/source/game_sa/Events/EventHandler.cpp).

## `earn_money`: maximize cash gained

Replaces `lose_wanted` in the intended task pack.

- **Objective:** Gather as much money as possible within two minutes.
- **Primary score:** Player cash at the end of the window minus player cash at
  the start, in in-game dollars; higher is better. Report both balances.
- **Allowed methods:** Kill NPCs and collect their dropped money, collect other
  available cash, or use other normal in-game earning activities that fit the
  documented scenario. The agent chooses its method.
- **Accounting:** Starting cash earns no credit. Cash on the ground counts
  only once collected and reflected in the balance. Spending and cash losses
  reduce the net score, which can be negative. A payout after the deadline does
  not count even if the activity began during the window.
- **Integrity:** Cheats, debug/host cash grants and changes to the starting
  balance during an attempt are outside the scoring contract.

The scorer records starting cash and the latest sampled balance strictly before
the deadline. Telemetry samples at 10 Hz: the endpoint balance has up to one
sampling interval of temporal quantization, disclosed as `cash_sample_tick_ms`.
A sample at or after the deadline cannot introduce a late payout. Starting and
ending balances are retained with the net integer score.

## Completion and reporting

`status=completed`, `reason=window_completed`, `score_complete=true` and
`elapsed_seconds=120` denote a completed scored window. There is no early-success
threshold. Death/arrest produce `incomplete` with a partial score and actual
elapsed time. Setup, capture, API and telemetry failures retain concrete failure
reasons and `score_complete=false` when scoring started. Artifact failures can
change overall status while preserving the frozen `task_status` and score.
The CLI rejects shortened timeout overrides for these two tasks.

Models continue to receive structured state. Local recording remains evidence
for review and never enters prompts. Adapters choose actions; the runner owns
controls, clocks and judgment. Any future shared assistance must be recorded
in controller provenance and described alongside scores.

Compare completed attempts using the distribution of kill counts or net cash
scores, with trial counts, incomplete attempts and infrastructure failures
reported explicitly. Completion-time rankings do not measure these fixed-window
objectives. See [results and methodology](results.md), [task authoring](adding-tasks.md)
and the [roadmap](roadmap.md).
