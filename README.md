# GTA Benchmark

An experimental benchmark for AI agents completing measurable tasks in Grand
Theft Auto. Models receive structured game state, take bounded actions, and are
evaluated by game-state rules. Every attempt produces a status, task time,
decision trace and local video evidence.

The current environment is **classic GTA San Andreas 1.0 US on Windows**. The
first adapter is **TypeSafe Jev**. The project, repository and Python distribution
are named `gta-benchmark`. The Python import package remains `sa_agent` for
compatibility with the existing runtime and native bridge.

## What works today

- Plugin-SDK bridge for player, vehicles, roads, driver doors and obstacle data.
- Five editable sample tasks with independent preconditions and evaluators.
- Jev integration using structured state. Screenshots, video and audio stay local.
- New Game preparation before a run, with opening-alley and BMX readiness checks.
- Task deadlines independent of model latency, rendering and video finalization.
- 1280 × 720 game profile, 30 FPS cap and constant-30-FPS local MP4 recording.
- Fifteen seconds of aftermath recording after success; task time stays frozen.
- Versioned results and a manifest with task/config fingerprints and provenance.

For `steal_car`, the model selects a target automobile and a shared local
controller handles road navigation, traffic interception and driver-door entry.
The other samples use primitive action choices. Report the controller mode
alongside the model when comparing results.

This is a development baseline. One recorded car-acquisition attempt succeeded;
the four other task policies still need live evaluation. See
[validation and limitations](docs/validation.md).

## Get started

Set up the game bridge and local configuration using the
[Windows setup guide](docs/setup.md). From the repository root, with the runtime
already installed:

```powershell
D:\SA-Agent\venv\Scripts\python.exe -m sa_agent validate
D:\SA-Agent\venv\Scripts\python.exe -m sa_agent run steal_car --reset new_game
```

The second command prepares New Game, waits for controllable CJ beside the
opening bicycle, runs the task and records its aftermath on success. The task
clock starts after preparation and recording startup. A loaded old ASI needs
one complete game exit before the updated bridge can be installed.

Replace `steal_car` with another task ID or a task JSON path. For an already
staged driving or wanted-level scenario, use `--reset none`.

Shared defaults live in [configs/benchmark.json](configs/benchmark.json).
Copy them to `configs/benchmark.local.json` for your own game path, FFmpeg and
optional proxy. The local file takes precedence and is ignored by Git. Credentials
belong in the environment or ignored `.env.local`.

After package installation, `gta-benchmark` and the compatible `sa-bench` entry
points expose the same CLI. `python -m sa_agent` continues to work. RTK can wrap
these commands where installed; it is not a runtime dependency.

## Task pack

The intended task pack replaces `park_and_exit` with `kill_npc` and
`lose_wanted` with `earn_money`. These two replacements are documented plans;
their task definitions, telemetry, evaluators and score output are not implemented.

| Task ID | Starting state | Goal / score | Task time | Availability |
| --- | --- | --- | --- | --- |
| `steal_car` | On foot outdoors near a reachable road | Drive an automobile for a 2-second hold | Up to 120 s | Implemented; model target selection + local navigation |
| `walk_to_waypoint` | On foot outside the configured goal | Stay within 4 m for 1 second | Up to 120 s | Implemented; primitive actions |
| `drive_100m` | Driving a working automobile | Travel 100 m in the same car | Up to 120 s | Implemented; primitive actions |
| `kill_npc` | Repeatable scenario with documented health, equipment and NPC availability | Maximize distinct NPC kills attributable to the player | Fixed 120 s | Planned; documentation only |
| `earn_money` | Repeatable scenario with documented starting cash and equipment | Maximize cash gained: ending cash minus starting cash | Fixed 120 s | Planned; documentation only |

The planned count and money benchmarks run for the full two minutes without a
target threshold or early success. Money may come from killing NPCs and collecting
their dropped cash, or other normal in-game earning methods. See the
[planned task contracts](docs/task-pack.md) for scoring and timing details.

The current runnable JSON pack still contains the legacy `park_and_exit`
(90-second limit) and `lose_wanted` (240-second limit) tasks. Fresh New Game
supplies an on-foot starting state; driving and the legacy parking/wanted tasks
require manual staging with `--reset none`. The runner does not manufacture
these scenarios. "Steal a car" is scored as taking an automobile's driver seat;
vehicle ownership history is not inferred.

## Documentation

| Goal | Guide |
| --- | --- |
| Install and configure the local environment | [Setup](docs/setup.md) |
| Find every command and config option | [CLI and configuration](docs/cli.md) |
| Understand the system and its boundaries | [Architecture](docs/architecture.md) |
| Add a task or success rule | [Task authoring](docs/adding-tasks.md) |
| Review the planned two-minute score benchmarks | [Task pack](docs/task-pack.md) |
| Add a model/provider adapter | [Agent authoring](docs/adding-agents.md) |
| Interpret outputs and compare runs | [Results and methodology](docs/results.md) |
| Understand New Game and extra recording | [Episode lifecycle](docs/episode-lifecycle.md) |
| Inspect car acquisition behavior | [Car acquisition](docs/car-acquisition.md) |
| Integrate with the native game data layer | [Bridge contract](docs/bridge.md), [telemetry tools](docs/telemetry.md) |
| Diagnose setup or runtime failures | [Troubleshooting](docs/troubleshooting.md) |
| Check current evidence and planned work | [Validation](docs/validation.md), [roadmap](docs/roadmap.md) |

## Development

These checks run without GTA, an API key or model requests:

```powershell
python tools/check_repo.py
python -m unittest discover -s tests -v
python -m sa_agent validate --config configs/benchmark.json
```

The native movement test is also available through CTest after a local Win32
build. GitHub Actions runs offline Python checks and the portable C++ movement
test. Full ASI builds require the separately installed Plugin-SDK and MSVC
toolchain. See [contributing](CONTRIBUTING.md) and [agent instructions](AGENTS.md).

## Repository layout

| Directory | Purpose |
| --- | --- |
| `sa_agent/` | Runner, configuration, agent adapters, navigation, evaluators and recording |
| `src/` | Win32 Plugin-SDK ASI and fixed-width shared-memory protocols |
| `reader/` | Basic read-only telemetry and optional localhost HTTP endpoint |
| `tasks/` | Five current versioned task definitions; planned replacements are in `docs/task-pack.md` |
| `configs/` | Public defaults, render profiles and ignored local overrides |
| `schemas/` | Task and result JSON contracts for tooling |
| `tests/` | Offline tests and native movement projection check |
| `tools/` | Build, installation, diagnostics and repository validation |
| `docs/` | Setup, architecture, extension guides and methodology |
| `runs/` | Ignored local results, traces and videos |

## License and attribution

Original repository code is [MIT licensed](LICENSE). GTA assets and third-party
dependencies are separate; see [third-party notices](THIRD_PARTY_NOTICES.md).
This community project is unaffiliated with Rockstar Games.
