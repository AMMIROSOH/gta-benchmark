# Adding tasks

A task defines a starting contract, a model instruction, allowed actions, a
deadline and a game-state success rule. The host decides success. A model's own
claim of completion never changes the result.

The current pack includes `kill_npc` and `earn_money`, described in
[task-pack.md](task-pack.md). Their fixed-window evaluator kinds are `npc_kills`
and `net_money`, each with only the `type` field, a mandatory 120-second timeout,
`fail_on_death=true` and `action_interface=agent_actions_v1`. They produce numeric
scores and never early success. Legacy parking/wanted definitions remain in
`tasks/legacy/` and can be loaded by ID or explicit path.

## Add a definition

Create a JSON file under `tasks/`, using a new unique ID. A complete example is:

```json
{
  "$schema": "../schemas/task.schema.json",
  "id": "reach_custom_point",
  "version": 1,
  "title": "Reach a custom point",
  "instruction": "Walk to the marked world position and remain there for one second.",
  "timeout_seconds": 120,
  "setup": "Start on foot outdoors within walking distance of the chosen point.",
  "preconditions": {"on_foot": true, "outside_goal": true},
  "success": {
    "type": "reach_waypoint",
    "position": {"x": 2290, "y": -1260, "z": 24},
    "radius_m": 4,
    "vertical_tolerance_m": 5,
    "hold_seconds": 1
  },
  "fail_on_death": true,
  "allowed_actions": ["idle", "forward", "backward", "left", "right", "sprint"]
}
```

Choose coordinates appropriate to your scenario. The waypoint example is in
Los Santos. `tags` is an optional list of unique strings. All other supported
fields are shown in the [schema](../schemas/task.schema.json); misspelled or
unknown rule fields are rejected.

```powershell
python -m sa_agent validate
python -m sa_agent run reach_custom_point --reset none
```

The first command is offline. Run the second only when you want a live attempt
and the documented starting state is staged. An explicit JSON path also works
without adding it to the built-in directory.

## Available preconditions

| Field | Requirement |
| --- | --- |
| `on_foot` | Player is outside a vehicle |
| `driving_automobile` | Player is the driver of vehicle subclass 0 |
| `nearby_automobile` | A living automobile appears in the nearby vehicle list |
| `minimum_speed_mps` | Initial speed at least this many metres/second |
| `minimum_wanted_level` | Initial wanted level at least 0–6 |
| `outside_goal` | Start outside a waypoint radius; only for `reach_waypoint` |

All tasks require a living player at staging. `on_foot` and
`driving_automobile` cannot both be required. New Game does not stage driving,
parking or wanted-level scenarios; use `--reset none` for those.

## Existing evaluator kinds

| `success.type` | Required rule fields | Scoring |
| --- | --- | --- |
| `enter_car_as_driver` | `hold_seconds` | Hold the driver seat of a living automobile |
| `reach_waypoint` | `position`, `radius_m`, `vertical_tolerance_m`, `hold_seconds` | Stay on foot within XY radius and Z tolerance |
| `drive_distance` | `distance_m`, `max_plausible_speed_mps` | Accumulate plausible XY movement in the starting car |
| `park_and_exit` | `stop_speed_mps`, `stop_hold_seconds`, `exit_hold_seconds`, `near_car_radius_m` | Stop, then exit and stay near that same car |
| `wanted_zero` | `hold_seconds` | Hold wanted level zero |

Distances are metres, speeds metres/second and durations seconds. Position uses
GTA world XYZ. Hold durations advance only with fresh samples. Loss of valid
state or pause suspends continuous holds. Arrest always fails; death fails when
`fail_on_death` is true. The runner separately handles deadlines, stale state,
focus loss, repeated API errors and recording failures.

## Actions and controllers

Use `action_interface=agent_actions_v1` for new tasks. The agent selects finite
movement, driving, interaction and combat controls; the host never chooses a
route or entry strategy. See [the action contract](agent-actions.md) for durations,
interruption, observations, normal GTA aim assistance and trace attribution.
The contracts below describe historical modes retained for compatibility.

Action names and descriptions live in `sa_agent/actions.py`. The current player
mode intersects the task's action set; `idle` must always be allowed. Primitive
walking is camera-relative and vehicle steering car-relative.

`world_walk`, `world_run` and `world_sprint` are available through the explicitly
declared `action_interface=bounded_movement_v1`, with agent-selected unit XY
directions and durations of 1–750 ms. This interface permits only world movement,
idle and jump, and supplies local geometry without a chosen route. See
[waypoint navigation](waypoint-navigation.md). Without that declaration these
actions retain their existing car-controller meaning. Car acquisition requires
`enter_exit` in its action set and retains its separate shared controller.

## Add a new success rule

1. Specify the observable goal, starting state, failure conditions, units and
   timing. Identify any additional telemetry the rule needs.
2. Add the kind and its field validation in `sa_agent/tasks.py`, then implement
   it in `TaskEvaluator.evaluate`. Return `Verdict` with progress, success or a
   concrete failure reason. Keep it independent of model/provider code.
3. Extend `schemas/task.schema.json`, this guide and relevant tests. Cover false
   positives, repeated/stale samples, interruption and boundary values.
4. Add a definition and run offline validation. Stage and evaluate a real run
   separately, keeping its result/video as evidence before claiming support.

Change the task version when instructions, actions, timeout, setup contract or
scoring semantics change. Keep task ID stable for the same conceptual task.
Changing metadata alone need not change the version; the manifest also hashes
the full definition. Never overwrite old results to make them appear to use a
new definition.
