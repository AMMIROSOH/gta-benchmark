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
| `confidence` | Provider confidence in `[0, 1]` |
| `probabilities` | Distribution over the offered choices |
| `model` | Actual provider response model/version when available |
| `usage` | Provider usage metadata; no credentials or raw headers |
| `observation_time` | Original host observation timestamp |
| `latency_seconds` | Measured request/decision duration |
| `allowed_actions` | Offered option labels; action names or car-choice labels |
| `plan` | Optional typed execution plan for the shared controller |

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

## Car target choices

For `success.type=enter_car_as_driver`, the runner supplies
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
key-only adapter needs this additional plan capability to run `steal_car`.

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
