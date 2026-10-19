# Roadmap

## Foundation in this repository

- Supported San Andreas state/control bridge and typed Jev integration.
- Independent episode timing, result/video artifacts and post-success recording.
- Host New Game preparation with acknowledged session/readiness checks.
- Five agent-owned task contracts, interruptible input and historical baseline modes.
- Engine-attributed kill events, combat pad inputs and fixed-window numeric scores.
- Offline validation/tests, extension guides and run provenance.

## Next: broaden validation and scenarios

The [task contracts](task-pack.md) replace `park_and_exit` with
`kill_npc` (maximize NPC kills in 120 seconds) and `lose_wanted` with
`earn_money` (maximize net cash gained in 120 seconds). Their runtime contracts
are implemented; scene coverage and representative model comparisons remain work.

1. Exercise positive and negative kill/cash accounting in more real scenes,
   including indirect damage, victim unloading and sampling/deadline boundaries.
2. Define repeatable starting fixtures for driving, combat and money gathering.
   Keep setup outside scored task time and document starting cash/equipment.
3. Validate each evaluator and policy in real gameplay, retaining failed runs,
   traces and finalized videos as evidence.
4. Exercise moving-traffic interception, blocked paths, failed entry and recovery
   across multiple scenes rather than relying on a single success.
5. Version task/scenario rules and document which reset modes can stage them.

## Then: controlled model comparisons

1. Add provider adapters through the existing decision contract, with mocked
   response tests and consistent observation/action interfaces.
2. Add a deterministic selection baseline to quantify shared-controller assistance.
3. Add batch manifests, trial counts, scenario assignment and explicit retry rules.
4. Add aggregation grouped by task version/hash, scenario, actual model and
   controller version. Report success rates and completion-time distributions
   for goal tasks, kill-count/net-cash distributions for fixed-window tasks,
   API latency and infrastructure failures.

## Later: broader environments

Additional GTA titles/versions need their own inspected game adapters, telemetry
contracts, control mappings and task validation. Preserve existing SA result
semantics while adding environments. The project/repository and distribution
name is `gta-benchmark`. Keep the existing `sa_agent` import package, native
`SAAgent` identifiers and installed D: runtime paths compatible; any later
package/ABI migration needs a separate compatibility plan.

Leaderboard hosting, visual model inputs, save-state management and deterministic
traffic control are future design decisions, not implemented features.
