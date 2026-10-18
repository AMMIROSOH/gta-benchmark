# Roadmap

## Foundation in this repository

- Supported San Andreas state/control bridge and typed Jev integration.
- Independent episode timing, result/video artifacts and post-success recording.
- Host New Game preparation with acknowledged session/readiness checks.
- Five sample task contracts and two explicit execution modes.
- Offline validation/tests, extension guides and run provenance.

## Next: complete the task pack

1. Define repeatable starting fixtures for each sample, including driving,
   parking and wanted-level scenarios. Keep setup outside scored task time.
2. Validate each evaluator and policy in real gameplay, retaining failed runs,
   traces and finalized videos as evidence.
3. Exercise moving-traffic interception, blocked paths, failed entry and recovery
   across multiple scenes rather than relying on a single success.
4. Version task/scenario rules and document which reset modes can stage them.

## Then: controlled model comparisons

1. Add provider adapters through the existing decision contract, with mocked
   response tests and consistent observation/action interfaces.
2. Add a deterministic selection baseline to quantify shared-controller assistance.
3. Add batch manifests, trial counts, scenario assignment and explicit retry rules.
4. Add aggregation grouped by task version/hash, scenario, actual model and
   controller version. Report success rates, completion-time distributions,
   API latency and infrastructure failures.

## Later: broader environments

Additional GTA titles/versions need their own inspected game adapters, telemetry
contracts, control mappings and task validation. Preserve existing SA result
semantics while adding environments. Rename filesystem/package/ABI identifiers
only as a planned compatibility migration; the repository is already branded
GTA Benchmark while `sa_agent` remains supported.

Leaderboard hosting, visual model inputs, save-state management and deterministic
traffic control are future design decisions, not implemented features.
