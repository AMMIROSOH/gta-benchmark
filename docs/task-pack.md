# Planned task pack

GTA Benchmark (`gta-benchmark`) will replace `park_and_exit` with `kill_npc`
and `lose_wanted` with `earn_money`. `steal_car`, `walk_to_waypoint` and
`drive_100m` retain their existing goals.

This document specifies future behavior only. The runnable JSON definitions,
schemas, bridge, actions, runner and result format still implement the current
tasks. Neither replacement can be run or scored yet.

## Shared two-minute scoring window

Both new tasks measure how much an agent achieves in exactly **120 seconds**.
A completed window produces a numeric score; reaching a particular count or
cash amount never ends the task early. Expiry is normal completion for these
planned benchmarks, whereas the current runner treats task timeouts as failure.

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

The current bridge and evaluators do not provide this verified kill-count
contract. Future implementation needs suitable structured telemetry, bounded
combat controls, an evaluator and a numeric result contract.

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

The existing state includes player cash, but the runner does not implement this
fixed-window money score. Future implementation needs start/end accounting,
numeric results and validation of the earning actions it exposes.

## Future implementation and reporting

Use new task IDs and versions for these distinct objectives; preserve the old
task definitions and results as historical evidence when implementing the
replacement. Extend task/result schemas, runner deadline handling, telemetry
and offline checks together before advertising either task as supported.

Models continue to receive structured state. Local recording remains evidence
for review and never enters prompts. Adapters choose actions; the runner owns
controls, clocks and judgment. Any future shared assistance must be recorded
in controller provenance and described alongside scores.

Compare completed attempts using the distribution of kill counts or net cash
scores, with trial counts, incomplete attempts and infrastructure failures
reported explicitly. Completion-time rankings do not measure these fixed-window
objectives. See [results and methodology](results.md), [task authoring](adding-tasks.md)
and the [roadmap](roadmap.md).
