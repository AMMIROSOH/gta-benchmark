# Adding model and provider adapters

The initial adapter is `jev`, using TypeSafe's typed Choice API. Select a
different supported TypeSafe model through `agent.model` or `run --model ID`.
Another provider needs a Python adapter registered in `sa_agent/agents/__init__.py`.
No additional provider integrations are implemented yet.

## Decision contract

An adapter is constructed with the effective `agent` config plus
`action_duration_ms`. It implements the `Agent` protocol from
`sa_agent/agents/base.py`:

```python
def decide(self, task, state, elapsed, progress, observation_time) -> Decision:
    ...
```

The worker makes one call at a time. `observation_time` is the host's monotonic
timestamp for the supplied state. Preserve it in the returned decision so the
runner can reject stale responses. The adapter returns data and never writes
game controls, resets a session, runs a task evaluator or captures frames.

| `Decision` field | Meaning |
| --- | --- |
| `action` | A permitted action name; car target choices return `idle` |
| `confidence` | Provider confidence in `[0, 1]`, or `None` if unavailable |
| `probabilities` | Distribution over the offered choices, or `None` if unavailable |
| `model` | Actual provider response model/version when available |
| `usage` | Provider usage metadata; no credentials or raw headers |
| `observation_time` | Original host observation timestamp |
| `latency_seconds` | Measured request/decision duration |
| `allowed_actions` | Offered option labels; action names or car-choice labels |
| `plan` | Optional typed execution plan for the shared controller |
| `parameters` | Explicit direction/duration for the bounded movement interface |

## Primitive choices

Use `available_actions(task, state)` to obtain the allowed current-mode choices.
Create compact structured context, issue a bounded request, validate its output
against those choices, and return a decision. A response outside the offered set
must fail rather than becoming an arbitrary input.

The Jev adapter supplies player/current vehicle/nearby world data, clock/weather,
task progress and recent decisions. It logs actual response versions, confidence,
probabilities, latency and usage. It validates finite probabilities and their sum.
Follow the provider's real response contract instead of fabricating confidence
or usage when a new provider does not supply them; extend the shared contract
deliberately if optional metadata is needed.

## Agent-directed movement

Current tasks use `action_interface=agent_actions_v1`. The runner passes the same
projected structured observation to all adapters, including NPC/pickup facts and
the currently executing command. Return a `Decision` with exact action parameters
as specified in [agent actions](agent-actions.md); `plan` must be null. Other
providers may output continuous unit XY directions and integer durations directly,
without Jev choice probabilities. The adapter owns all task strategy and recovery.

For historical `action_interface=bounded_movement_v1`, the runner passes the shared
observation projection to every adapter and executes only explicit short commands.
Return an allowed `action`, `plan=None` and `parameters` containing an integer
`duration_ms` in 1–750 plus a finite unit `direction_world_xy` for world movement.
`idle` and `jump` take only the duration. There is no route/target plan.
The agent owns navigation and recovery. The Jev adapter discretizes the same
interface into fixed directions and durations; another provider can supply
parameters directly. Keep the discretization equal when comparing models.
See the complete [waypoint observation and action contract](waypoint-navigation.md).

## Historical assisted car target choices

For historical `success.type=enter_car_as_driver` definitions without
`action_interface=agent_actions_v1`, the runner supplies
`progress["navigation_controller"]["candidates"]`. Each candidate has an actual
vehicle pool reference, route cost, speed, occupation and approach strategy.
Ask the model to select one offered reference or wait, then return `action=idle`
with this plan:

```python
plan = {
    "type": "acquire_automobile",
    "target_vehicle_reference": selected_reference,  # int, or None to wait
    "selection": f"car_{selected_reference}" if selected_reference is not None else "wait",
}
```

The host revalidates the reference against current eligible candidates before
accepting it. The shared controller retains it until acquired, unavailable or
blocked. It executes movement and entry independently of API latency. A primitive
key-only adapter needs this plan capability for that historical assisted mode.
Current steal-car v5 rejects such plans and uses the ordinary agent-action contract.

## Register and configure

1. Add `sa_agent/agents/your_provider.py` with the adapter class and its own
   provider transport. Keep imports lazy when dependencies are optional.
2. Add `"your_provider": ("sa_agent.agents.your_provider", "YourAgent")` to `AGENTS`.
3. Extend configuration validation for provider-specific settings. Shared timing,
   task, recording and reset settings belong outside provider code.
4. Store credentials in environment variables or an ignored local file. Keep
   secrets out of `Decision`, config snapshots, manifests, errors and prompts.
5. Add mocked transport tests for option construction, invalid responses, stale
   observations and errors. These tests must not call a real service.
6. Validate offline, then run the same versioned scenarios/controller settings
   when an actual comparison is requested.

`python -m sa_agent agents` lists registered names without instantiating them.
There is no arbitrary module path loading through JSON config; registration is
an explicit source change.

## Comparison boundaries

Keep task instructions, actions, timing, controller version, scenario preparation
and available observations constant between models. Report the actual model
versions and whether execution used primitive actions or shared navigation.
Measure latency and failures as part of the experiment. The existing hybrid
car task evaluates model selection with shared assistance; its result alone
does not establish a model's independent navigation ability.

See [results and methodology](results.md) for grouping and reporting runs.
