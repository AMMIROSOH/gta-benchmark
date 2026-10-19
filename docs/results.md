# Results and benchmark methodology

Every `run` creates `runs/<task_id>/<UTC timestamp>-<run_id>/`. Old artifacts
remain immutable. Setup failures still produce a result even if recording and
the task clock never started.

```text
result.json                      terminal task/run outcome and timing
manifest.json                    source, task/config hashes and runtime provenance
task.json                        exact task definition used
config.json                      effective config, without an API key
initial_state.json               state at task start, when reached
observations.jsonl               structured task observations
actions.jsonl                    model choices, controller inputs and errors
reset.json                       New Game preparation result, when enabled
reset_events.jsonl               acknowledged native reset phases
post_success_observations.jsonl  aftermath observations, on success
video.mp4                        finalized local CFR recording
ffmpeg.log                       encoder diagnostics
```

An interrupted/failed encode can leave `video.partial.mp4`. Treat only a
finalized video as complete evidence. Runs and recordings are ignored by Git;
publish selected, reviewed experiment artifacts separately when appropriate.

## Task verdict and artifact completion

New results use [schema version 1](../schemas/result.schema.json).

| Field | Interpretation |
| --- | --- |
| `status`, `reason` | `success`, `completed`, `incomplete` or `failed`, and concrete reason |
| `task_status`, `task_reason` | Frozen task verdict before recording/cleanup errors |
| `task_id`, `task_version` | Evaluated definition and scoring version |
| `elapsed_seconds` | Monotonic task time; excludes preparation, recording startup, aftermath and finalization |
| `started_at_utc`, `finished_at_utc` | Task start and terminal boundary; start is null on setup failure |
| `artifacts_status` | `finalizing`, `complete` or `failed` |
| `artifacts_finished_at_utc` | End of video finalization and cleanup |
| `agent`, `requested_model`, `models_used` | Adapter, requested model and response model versions seen |
| `policy_mode` | Current `agent_actions`; historical `primitive_actions`, `bounded_movement`, `target_selection_with_road_controller` |
| `action_interface`, `executor_version` | Explicit bounded movement contract and mechanical executor version, when used |
| `invalid_commands_dropped` | Bounded commands rejected for malformed parameters or unsupported plans |
| `decision_count`, `observed_decision_hz` | Completed decisions and rate during task time |
| `navigation_control_ticks`, `observed_navigation_control_hz` | Shared controller work and actual rate |
| `stale_decisions_dropped` | Responses rejected for age |
| `task_progress`, `final_state` | Goal progress and state at the terminal task boundary |
| `reset` | Separate preparation metadata, or null |
| `post_success_recording` | Requested/actual extra recording, completion/interruption and aftermath state |
| `video` | File path, CFR/frame counts, captures/duplicates, errors and task offsets |

The preliminary result is saved when the task ends. Wait for
`artifacts_status=complete` or a terminal artifact failure before consuming the
run as finalized. A video error can make overall `status=failed` while preserving
`task_status=success`. A post-success interruption alone preserves the goal
verdict and is reported in its own metadata.

Timeouts count active wall time, including temporary pauses and model latency.
A setup/precondition failure has zero task time. It is not a zero-second task
completion. The agent cannot extend its task deadline by issuing another request.

## Manifest

`manifest.json` includes benchmark/schema versions, environment ID, source commit
and dirty status, task ID/version/SHA-256, effective config SHA-256, policy mode,
controller version, requested model, Python/OS/architecture, installed package
versions, and game/ASI binary hashes when available. Task hashing excludes the
machine-specific `source_file` field. Config hashing covers the complete effective
config, so changes to timing, proxy, recording and local paths are detectable.

New manifests also include `runtime_source_sha256` for the Python runtime,
reader and native source files, so an adapter/prompt revision in a dirty checkout
can be distinguished. Bounded movement records its action interface and executor
version separately from `controller_version=null`.

A missing Git checkout or unavailable binary is represented by null metadata;
it does not pretend to be a clean, pinned environment. A dirty checkout needs
its source snapshot to reproduce the run. Configuration and task snapshots are
retained alongside the hashes.

Historical runs created before this schema have no `schema_version` or manifest.
They may use `jev_primitive_actions` and
`jev_target_selection_with_road_controller` mode labels. Keep those artifacts in
their original form and identify them as legacy when analyzing them.

## Decision traces

Current [agent-action](agent-actions.md) traces distinguish `agent_action`
authorizations from `authorized_command_lease` writes. Every lease has a parent
command ID, native request ID and authorization end; it cannot extend that end
or change the authorized endpoint. `applied_actions` counts agent commands and
`native_input_leases` counts writes. Shared navigation ticks remain zero.
The following target-selection/controller fields describe historical modes.

`actions.jsonl` separates model target selections from navigation-controller
ticks. Entries include timing, selection/action, acceptance/drop reason, request
ID, confidence/distribution and actual model when available. Native control
acknowledgement is checked by the runner. A model response is not evidence that
the game applied the requested action.

Bounded movement entries use `source=agent_action` and include the selected
parameters, actual leased `duration_ms` and execution `goal`. The goal is a
mechanical projection of the selected direction, not a host-selected waypoint.
There are no shared navigation ticks in this mode. Optional confidence and
probabilities may be null for adapters whose providers do not supply them.

The independent recorder writes a constant-frame-rate file. Repeated frames can
occur when no fresh game frame is presented or foreground is temporarily lost;
the video metadata reports captures and duplicate ticks. A 30-FPS file does not
prove 30 distinct simulation observations per second. Keep frame rate, task
time and model decision rate separate.

## Comparing models

The `kill_npc` and `earn_money` tasks use fixed 120-second windows and
numeric scores: distinct attributable NPC kills and ending cash minus starting
cash, respectively. Compare score distributions across completed windows and
report incomplete attempts separately. Their deadline is normal completion,
with no early success threshold. `score`, `score_unit` and `score_complete`
accompany start/end cash, scored event evidence and window tick bounds. Only
`completed` windows have `score_complete=true`; see [task contracts](task-pack.md).

For a comparison, specify the task version/hash, game/bridge versions, source
revision, scenario preparation, observation/action interface, model versions,
controller mode/version, timing and recording settings. Use multiple attempts
per model with the same protocol and retain failed attempts as well as successes.

For the currently implemented goal tasks, report success rate and completion-time
distribution together. Completion time
on successes alone omits failures and timeouts; identify that denominator clearly.
Report preparation/infrastructure/API failures separately from goal failures,
with the exclusion policy fixed before collecting results. Describe any retries.

New Game resets story progress and location, but traffic and pedestrians remain
stochastic. `scenario_deterministic=false` records this limitation. Repeated runs
at the same opening location are not guaranteed identical traffic scenes.
Saved scenario fixtures, controlled seeds and batch/leaderboard tooling are
[planned work](roadmap.md).

The single historical steal-car success is integration evidence, not a model
ranking or an estimate of success probability. See [validation](validation.md).
