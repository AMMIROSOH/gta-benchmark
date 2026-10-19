# Validation and current limitations

The repository is an experimental benchmark foundation. Offline tests establish
specific contracts; live recordings establish what happened in individual
attempts. Neither alone establishes a model-wide success rate.

## Recorded integration evidence

### Interruptible agent actions, 2026-10-19

Current waypoint v3, steal-car v5, drive v2, kill-NPC v1 and earn-money v1 use
[agent-owned actions](agent-actions.md). The source passed 60 offline tests,
both task/result schemas, the Win32 ASI build and two portable CTest checks
(camera projection and distinct attributed victim lifetimes).

With Jev's explicit held-control vocabulary, waypoint v3 succeeded in **32.80 s**
in `runs/walk_to_waypoint/20261019T111142-d4a55f2a/`. All 21 agent commands were
acknowledged. There were 240 short native leases and zero shared navigation ticks.
The first input began at 1.609 s; after that there were **zero gaps between native
leases**. Input coverage was 31.188 s of the 32.797-s task. Jev selected walking,
not running. The complete video decoded successfully and a mid-run frame was
reviewed. All 40 runtime source hashes matched the retained source archive in
`runs/validation/agent-actions-20261019/runtime-held-controls-initial.zip`.

Earlier duration-menu development runs succeeded in 23.16 s, 21.84 s and 84.56 s,
but Jev selected short holds that still left inference gaps. They do not prove
the final continuity fix and remain separate evidence. A later warm reset failed
capture startup (`20261019T110949-45844505`) before task time or model calls.

An agent-action steal-car attempt (`20261019T110529-2a98b96f`) failed with player
death at 55.17 s. Jev repeatedly pressed entry without approaching a door; all
28 pulses were acknowledged and there were no navigation-controller ticks. This
is a policy failure under the new contract, not the older assisted success below.

`tools/validate_task_live.py --live` is a separate, explicitly labeled scripted
adapter for integration checks. Its policy is outside the runner/executor, uses
the same public observations/decisions, grants no game state and makes no model
requests. Fixture outcomes are not Jev performance or AI success rates. Its first
kill-NPC attempt ended on arrest at 15.53 s with partial score 0 and
`score_complete=false`; it started from a manually staged, already damaged player.
The failed fixture car attempt timed out at 120.05 s. Both videos decoded and
their leases passed the audit. These failures are retained rather than excluded.

A subsequent kill-NPC fixture completed exactly 120 s with score 0 in
`runs/validation-fixtures/kill_npc/20261019T112246-d49d95f3/`. The money fixture
in `runs/validation-fixtures/earn_money/20261019T112715-de9d01fd/` also completed
exactly 120 s with score 0 (cash stayed 350). Both finalized videos decoded and
all 567/562 commands respectively were acknowledged. The money attempt killed
NPC reference 6147: the engine event identifies player-ped melee attribution,
and independent samples show its health reaching zero and dead state 55.
The event remains after that NPC unloads. No money pickup appeared for that
victim, so this is not positive cash-collection evidence.

Replaying those recorded money-task observations through the kill evaluator
produced exactly one kill, with no missing-event errors; the report is retained
as `runs/validation/agent-actions-20261019/positive-kill-replay.json`. This is
positive validation of the evaluator against real game events, not a new scored
kill-task attempt or an AI-performance result.

Steal-car v5 adds explicit jump/climb to the agent action set. A manually staged
scripted-fixture attempt completed in **14.00 s** in
`runs/validation-fixtures/steal_car/20261019T113715-0dc5f422/`: the final state
and the recorded aftermath confirmed automobile driver reference 6413/model 566,
with a healthy player and car. All 66 commands were acknowledged, the 128 leases
passed attribution/deadline checks, and the full video decoded. There were zero
shared navigation ticks. This validates agent-owned execution with a scripted
policy; it is not a Jev success. Earlier fixture timeouts remain retained.

After the session-deduplication fix, a fresh fixture acquisition succeeded in
20.09 s (`runs/validation-fixtures/steal_car/20261019T114559-f8d061f8/`). The
validation tool immediately staged a separate driving episode in that acquired
taxi; the ordinary task runner does not chain tasks. `drive_100m` completed
**100.48 m in 13.52 s** in
`runs/validation-fixtures/drive_100m/20261019T114828-b2d4930c/`. All 95 acquisition
and 64 driving commands were acknowledged, both full videos decoded, and neither
run used shared navigation ticks. Their 40 runtime hashes and fixture-policy hash
matched the archived source used for those runs. These are scripted integration results.
Cash rose from 350 to 362 during that acquisition. A separate partial replay
through the money evaluator records **+12**, with `score_complete=false`, in
`runs/validation/agent-actions-20261019/positive-money-partial-replay.json`.
This validates positive balance accounting on real gameplay; it is not a
completed 120-second money attempt or evidence of collecting a dropped pickup.

Use `tools/audit_agent_run.py RUN_DIRECTORY --decode-video` to independently check
command attribution, frozen endpoints, lease bounds, acknowledgements and video
decoding. Zero input gaps describes this one held-control run; API stalls, stale
responses, deliberate idle choices and collision/animation effects can still stop
movement. Broader scene and provider performance remains unmeasured.

### Agent-directed waypoint task, 2026-10-19

`walk_to_waypoint` version 2 uses the
[bounded movement interface](waypoint-navigation.md), with every movement
direction, pace and duration chosen by the agent. Local code projects each
command into one expiring input lease. No shared navigation controller is used.

The first scored Jev attempt,
`runs/walk_to_waypoint/20261019T094248-b7c4fcc7/`, timed out at 120.00 seconds.
It started 50.31 m from the waypoint and finished 23.53 m away. There were 66
completed decisions, 61 applied commands, five stale drops, no invalid commands
and zero shared navigation ticks. All 61 commands were acknowledged in telemetry.
Jev selected 200 ms run inputs throughout, with median response latency 1.62 s.
The complete video decoded without errors. This is live evidence of the command
boundary and of a failed policy attempt, not successful waypoint navigation.

After that attempt, the adapter's timing description was clarified: button-hold
duration is distinct from model response latency, and expired inputs stay
released. A diagnostic replay of the original starting observation selected a
400 ms run input; the replay applied no game controls and is not a scored result.

With the clarified timing description, the standard task succeeded in
**100.77 seconds** in `runs/walk_to_waypoint/20261019T095358-a5095e6b/`.
It started 50.31 m from the goal and finished 3.80 m away. There were 58
decisions, 55 applied/acknowledged commands, three stale drops, no invalid
commands and zero shared navigation ticks. Jev selected 42 inputs of 400 ms
and 13 of 200 ms. The complete video decoded without errors; it contains
duplicate frames and is not evidence of 30 distinct observations per second.
All 34 runtime source hashes in its manifest matched the inspected source.
This establishes one live completion under this interface, not a success rate
or general obstacle-navigation ability.

A repeat with the same task, action menu, adapter and 120-second task deadline
succeeded in **84.61 seconds** in
`runs/walk_to_waypoint/20261019T095903-55001e78/`. It finished 3.87 m from the
goal with 52 applied/acknowledged commands, no stale or invalid drops and zero
shared navigation ticks. Jev chose 41 inputs of 400 ms and 11 of 200 ms. Its
complete video decoded without errors. Cold-start validation used a run-only
config with a 180-second preparation deadline; the scored task budget was
unchanged. UI input used to dismiss startup movies occurred before scoring.

The exact 34 runtime source files for these successes are retained locally in
`runs/validation/waypoint-20261019/runtime-source.zip`; the accompanying
`evidence.json` records outcomes and video hashes. These are development checks,
not a representative scenario sample or a published model success-rate estimate.

An alternate goal at `(2263.25, -1249, 24)`, corresponding to a nearby pedestrian
node, succeeded in **58.45 seconds** in
`runs/walk_to_waypoint_diagonal_validation/20261019T100330-02e08469/`.
It used the same interface, adapter, action menu and task deadline, with only
the waypoint/scenario metadata changed. The start was 26.84 m from this goal;
the final distance was 3.79 m. All 35 commands were acknowledged, with zero
stale/invalid drops and no shared navigation ticks. Jev selected 24 eastward
commands followed by 11 northward commands, all 400 ms; no host route was
provided. Its video decoded completely and its source hashes matched the same
archive. The last continuous on-foot goal holds reconstructed from telemetry
were 1.078 s, 1.031 s and 1.032 s for the three successful runs respectively.

Both JSON Schemas were checked with an existing JSON Schema implementation:
all five public task files and nine result files passed, and undeclared world
actions and incompatible action/interface combinations were rejected.

Other attempts failed before the task clock started: cold-start preparation at
game state 4 (`20261019T094020-829bec3c`, `20261019T094906-7a1228de`) and recording
startup with no captured frames (`20261019T094537-c82b7fec`,
`20261019T094635-3e2b9dfc`, `20261019T095636-9dea194b`). Keep these infrastructure failures separate from the
scored timeout. Infrastructure failures are not completed policy evaluations.

`tools/audit_waypoint_run.py` checks command attribution, requested direction
versus executed goal, lease bounds, telemetry acknowledgements and optional full
video decoding without connecting to GTA or a model:

```powershell
rtk proxy D:\SA-Agent\venv\Scripts\python.exe tools/audit_waypoint_run.py runs/walk_to_waypoint/20261019T094248-b7c4fcc7 --decode-video
```

The source/runtime contracts passed 45 offline Python tests, repository checks,
public config/task validation and the portable native movement projection test.
The runner simulation includes an agent-supplied detour around a wall, a blocked
policy that cannot receive automatic recovery, silent-agent command expiry,
stale/invalid-command rejection and final-lease deadline truncation. These are
specific implementation checks. The live completion above provides the separate
integration evidence; broader navigation performance remains unmeasured.

### Assisted car acquisition, 2026-10-18

On 2026-10-18, `steal_car` version 3 with `jev-1.14.0` and the shared road/door
controller succeeded in **29.30 seconds** within a 120-second limit. The selected
vehicle reference was 12033, model 554; final telemetry matched that vehicle and
confirmed the driver role for 2.03 seconds. There was one enter/F pulse, no API
errors and no native sampling errors. The 1280×720 H.264 video contained 879
frames at constant 30 FPS and decoded completely without errors.

That local artifact directory is
`runs/steal_car/20261018T170731-c70911dd/`. Artifacts are retained locally and are
not bundled with the source. This run used a stopped car and predates the New
Game/aftermath extensions and provenance schema. Moving-traffic interception was
not exercised in that live success. The other three legacy primitive sample
policies have no verified live results recorded here. Waypoint version 2 has
the separate successful and failed attempts above.

Earlier primitive-policy attempts failed due to direct-route API timeouts and,
after a working proxy route, a task timeout. Those older policies/modes are not
equivalent to the current assisted car-selection baseline. Their results remain
in their original local directories rather than being rewritten as current runs.

## Offline coverage

The tests cover navigation candidate filtering, stable vehicle references,
road routing, rotated-car detours, bounded traffic waits, one-shot entry,
animation handling and simulated convergence. Contract tests also cover task
validation, false-positive driver/bicycle cases, hold freshness, distance
discontinuities, local config selection and reproducibility fingerprints.
Windows-only orchestration tests mock every game/model/capture operation and
verify frozen success timing, aftermath interruption, host reset acknowledgement
and rejection of an old session generation. They never connect to a live game.

The portable C++ movement test checks the bridge's world-direction projection
against an independently reconstructed game movement formula across camera
angles. Full native sampling, renderer hooks, DXGI capture, model connectivity
and New Game behavior need separate checks in the supported installed game.
The standard offline suite and CI do not launch GTA or call a model.

## Limits to account for

- `kill_npc` and `earn_money` implement engine event attribution and fixed-window
  scores. Distinguish offline scoring checks, positive gameplay events and full
  completed windows when interpreting the live evidence; see [task pack](task-pack.md).
- Only classic GTA SA 1.0 US is supported by the inspected hooks and structures.
- Nearby entities, loaded road nodes and local probes are bounded; there is no
  global route map or complete world perception.
- Historical car acquisition v3 shares a local controller; current v5 does not.
- Traffic may refuse to stop, paths may be blocked, and native entry can fail.
- New Game does not seed identical traffic or stage the other task scenarios.
- The driver-seat rule does not infer legal ownership or prove a carjacking.
- Target rates are schedules; actual API/control rates vary and are logged.
- CFR video can contain duplicates; recording is silent and window-position sensitive.
- DXcam 0.3.0 has a known local COM cleanup warning; artifact integrity must be
  checked from finalization/error data and, for published evidence, the video.

Use [results and methodology](results.md) when reporting comparisons and the
[roadmap](roadmap.md) for the next development steps.
