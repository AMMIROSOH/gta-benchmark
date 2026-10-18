# Working on GTA Benchmark

Read [README.md](README.md), [architecture](docs/architecture.md) and the relevant
extension guide before changing behavior. `sa_agent` and the native `SAAgent`
mapping names are intentional compatibility identifiers.
The project/repository and distribution name is `gta-benchmark`.

## Scope and runtime

- Current game support is classic GTA SA 1.0 US on Windows. Do not claim other
  titles/versions are supported without an inspected adapter and validation.
- Preserve the working native bridge, user configuration, credentials, installed
  game/mods and local run artifacts. Use the installer for ASI deployment.
- Default development checks are offline. Do not launch/reset the game, make
  paid/authenticated model requests or start a task unless the user requests it.
- Source/output files stay in the project. Dependency downloads, caches, runtime
  and backups stay on D: with the existing tools. Reuse the installed C++ toolchain.
- Use RTK to prefix shell commands when it is installed in the working environment.

## Boundaries

- Models receive structured state. The local recorder's frames do not enter prompts.
- The planned `kill_npc` and `earn_money` replacements are specified in
  [docs/task-pack.md](docs/task-pack.md) only. Their implementation is separate
  work; keep the current JSON tasks and runtime behavior intact for documentation changes.
- Adapters return decisions; the runner owns controls, task clocks and judgment.
- `steal_car` uses model target selection plus shared navigation. Keep this
  assistance visible in results and documentation.
- Reset preparation and aftermath recording never add to scored task time.
- Native layouts use fixed-width fields and seqlocks; update both languages and
  docs together. Preserve process ownership, bounded inputs and expiry checks.
- Keep secrets in ignored environment/local files. Never print real keys in
  commands, diagnostics, tests, snapshots or commits.

## Required checks for relevant changes

```text
python tools/check_repo.py
python -m unittest discover -s tests -v
python -m sa_agent validate --config configs/benchmark.json
```

For native changes, also build with the existing Win32 toolchain and run the
portable movement test through CTest. Full game tests are a separate operation.
Update schemas, task versions, controller provenance and docs when their
semantics change. Keep claims proportional to the evidence actually collected.
