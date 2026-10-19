# Agent-directed waypoint navigation

**Historical v2 contract.** Current waypoint v3 uses the interruptible
[agent-actions interface](agent-actions.md). The non-renewing v2 design below
remains documented for its recorded results and compatibility tests.

`walk_to_waypoint` version 2 uses `action_interface=bounded_movement_v1` and
`policy_mode=bounded_movement`. The agent chooses every direction, pace,
duration, detour, jump and wait. The benchmark has no waypoint route planner,
automatic obstacle avoidance, movement renewal or recovery policy.

The goal remains on-foot presence within 4 m horizontally and 5 m vertically of
the configured point for one continuous second, with a 120-second wall-time
deadline. Fresh New Game starts in the opening alley; the default goal is
`(2290, -1260, 24)`. Version 1 used camera-relative primitive choices and is a
different evaluation condition. Historical artifacts are unchanged.

## Shared observation contract

The runner projects state before passing it to **any** adapter. The observation
contains player state, current vehicle, clock/weather, camera forward XY, nearby
vehicle identity/position/health/speed/body geometry, 16 world-direction clearance
and ground-height probes, and up to 96 local road/pedestrian nodes with positions,
visibility and links. Nearby entities are not filtered by suitability for the task.
Nodes are ordered by reference, not distance to the task goal. The source sensor
has local spatial limits; this is neither a global map nor visual perception.

Car controller fields, candidate rankings, route costs, proposed strategies,
interception points and door anchors are omitted. The model receives the goal and
evaluator progress, but no selected route or recommended next direction.
The recorder's images remain local and never enter prompts.

The native sensor's graph includes geometry-checked connections between nearby
road and pedestrian nodes, and its clearance probes account for ground changes.
These are shared geometry observations. The executor never consults that graph
or those probes to choose or change a command.

## Shared command contract

Adapters return a `Decision` with an allowed `action` and `parameters`. For example:

```python
Decision(
    action="world_walk", confidence=None, probabilities=None,
    model="my-agent", usage={}, observation_time=observation_time,
    latency_seconds=latency, allowed_actions=(),
    parameters={"direction_world_xy": {"x": 0.6, "y": 0.8}, "duration_ms": 400},
)
```

`world_walk`, `world_run` and optionally `world_sprint` require a finite unit XY
direction and an integer duration of 1–750 ms. `idle` and `jump` take only
`duration_ms`. The task's allowed action set still applies. Jump is the existing
camera-forward jump/climb input, not an automatic climb route.

The executor converts a movement direction into one fixed point 3 m from the
player at application time, with a 0.1 m stopping radius, and sends one input
lease. It releases on expiry or earlier if that point is reached. The native
hook projects the direction into pad axes using camera orientation each frame.
An accepted subsequent agent command can supersede the current lease.
Normal collision and animation behavior remains in the game. The point is not
a pathfinding destination: an obstacle is never routed around by the executor.
The executor does not have access to the task goal, road graph or decision history.

The runner rejects stale, disallowed or malformed commands and does not replace
them with a better movement. Commands cannot contain target references, routes,
arbitrary coordinates or execution plans. No command is renewed while the model
is busy. Model latency and idle gaps count against task time. Final input leases
are shortened to the remaining task window.

## Jev and other agents

The Jev adapter presents a fixed, unranked menu: 16 world directions × three
durations (200/400/600 ms) for each permitted movement pace, plus idle and jump
durations. The default task has 102 options. Options are never removed because
they point into a wall or away from the goal. Jev chooses one entire command;
the host does not assemble a strategy from its confidence values.

Other adapters can return parameterized commands directly. Confidence and
probabilities may be `None` when a provider does not supply them. For a controlled
model comparison use the same action discretization, observation projection,
memory policy and budgets. A complete agent may bring its own planner; describe
and attribute that planner to the submitted agent, not to the benchmark.

## Evidence and reproducibility

The result records `bounded_movement`, the action interface, executor version,
invalid/stale drops and zero shared navigation ticks. The manifest records
`controller_version=null` and `executor_version=world_input_v1`. Action traces
contain the model's parameters, the actual leased duration, fixed execution goal
and request ID. New entries also include the execution origin and sample counter.
Raw local observations remain separate from the model projection. Runtime source
hashes in the manifest distinguish adapter/prompt revisions in a dirty checkout.

Offline tests cover malformed/expired commands, fixed option sets, observation
projection, foreign-provider parameters and runner attribution. An independent
collision/lease simulator checks that a blocked policy stays blocked, a silent
policy stops after one command, and an agent-supplied detour can succeed without
constructing a shared navigator. The portable native test checks camera projection.
These checks establish specific boundaries; they do not establish live model
navigation performance. Live evidence and limitations belong in
[validation](validation.md).

The initial live checks completed the standard waypoint twice (100.77 s and
84.61 s) and an alternate waypoint requiring eastward then northward movement
(58.45 s). All 142 applied commands across these successes were acknowledged,
with zero shared navigation ticks. This establishes functioning agent-directed
execution in those scenarios. Broad obstacle-navigation ability and a model-wide
success rate require a larger held-out scenario set. The initial scored timeout
and preparation/capture failures remain documented alongside the successes.
