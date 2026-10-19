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

All five current tasks use [agent-owned actions](docs/agent-actions.md). The agent
chooses every movement, duration, vehicle approach, entry attempt and combat
action. Finite commands can continue during the next model request; short native
leases preserve expiry and interruption. No shared route or car-entry controller
runs in this mode. Normal GTA collisions, animations and targeting still apply.

This is a development baseline. The [recorded results](#recorded-results) below
separate model performance from scripted integration checks and identify the
task versions used. See [validation and limitations](docs/validation.md) for
individual attempts, retained failures and evidence details.

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

The current pack replaces `park_and_exit` with `kill_npc` and
`lose_wanted` with `earn_money`. All five definitions are runnable.

| Task ID | Starting state | Goal / score | Task time | Availability |
| --- | --- | --- | --- | --- |
| `steal_car` | On foot outdoors near a reachable road | Drive an automobile for a 2-second hold | Up to 120 s | Agent-owned approach and entry |
| `walk_to_waypoint` | On foot outside the configured goal | Stay within 4 m for 1 second | Up to 120 s | Implemented; agent-directed bounded movement |
| `drive_100m` | Driving a working automobile | Travel 100 m in the same car | Up to 120 s | Agent-owned pad controls |
| `kill_npc` | On foot with documented health/equipment | Maximize distinct engine-attributed NPC kills | Fixed 120 s | Actor telemetry and numeric scoring |
| `earn_money` | On foot with documented cash/equipment | Maximize ending cash minus starting cash | Fixed 120 s | Numeric scoring, negative values allowed |

The count and money benchmarks run for the full two minutes without a
target threshold or early success. Money may come from killing NPCs and collecting
their dropped cash, or other normal in-game earning methods. See the
[task contracts](docs/task-pack.md) for scoring and timing details.

The `tasks/legacy/` folder preserves `park_and_exit`
(90-second limit) and `lose_wanted` (240-second limit) tasks. Fresh New Game
supplies an on-foot starting state; driving and the legacy parking/wanted tasks
require manual staging with `--reset none`. The runner does not manufacture
these scenarios. "Steal a car" is scored as taking an automobile's driver seat;
vehicle ownership history is not inferred.

## Recorded results

Selected development attempts as of **2026-10-19**, on classic GTA San Andreas
1.0 US for Windows. Times exclude reset preparation and aftermath recording.
These individual attempts do not establish a success rate or leaderboard.

| Current task | Jev `jev-1.14.0` | Scripted integration adapter |
| --- | --- | --- |
| `walk_to_waypoint` v3 | **Success: 32.80 s** | — |
| `steal_car` v5 | No v5 model run recorded | **Success: 20.09 s** from fresh New Game |
| `drive_100m` v2 | No model run recorded | **Success: 100.48 m in 13.52 s** |
| `kill_npc` v1 | No model run recorded | Full **120 s** completed; **0 kills** |
| `earn_money` v1 | No model run recorded | Full **120 s** completed; **0 net game dollars** (350 → 350) |

The waypoint model run acknowledged all 21 agent commands and had zero native
input-lease gaps after the first input at 1.61 s. An earlier Jev `steal_car` v4
attempt **failed: player died at 55.17 s**. Version 5 subsequently added
agent-selected jump/climb; its recorded successes so far use the scripted adapter.

The scripted adapter exercises the same public observations and actions without
model calls. Its results validate execution and scoring; they are separate from
AI performance. The driving episode was staged in the taxi acquired by the
preceding scripted car attempt, with its own task clock. Zero kill/money scores
are completed scoring windows, not positive-score demonstrations. Historical
assisted-controller runs and partial score replays are documented separately in
the [validation record](docs/validation.md#interruptible-agent-actions-2026-10-19),
along with run IDs, failures and source provenance. Raw traces and videos remain
local in ignored `runs/` directories.

## Documentation

| Goal | Guide |
| --- | --- |
| Install and configure the local environment | [Setup](docs/setup.md) |
| Find every command and config option | [CLI and configuration](docs/cli.md) |
| Understand the system and its boundaries | [Architecture](docs/architecture.md) |
| Add a task or success rule | [Task authoring](docs/adding-tasks.md) |
| Review the two-minute score benchmarks | [Task pack](docs/task-pack.md) |
| Inspect agent actions and latency handling | [Agent actions](docs/agent-actions.md) |
| Add a model/provider adapter | [Agent authoring](docs/adding-agents.md) |
| Interpret outputs and compare runs | [Results and methodology](docs/results.md) |
| Understand New Game and extra recording | [Episode lifecycle](docs/episode-lifecycle.md) |
| Inspect car acquisition behavior | [Car acquisition](docs/car-acquisition.md) |
| Inspect agent-owned waypoint navigation | [Waypoint navigation](docs/waypoint-navigation.md) |
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

Native movement projection and kill attribution checks are also available
through CTest after a local Win32 build. GitHub Actions runs offline Python
checks and both portable C++ tests. Full ASI builds require the separately
installed Plugin-SDK and MSVC toolchain. See [contributing](CONTRIBUTING.md) and
[agent instructions](AGENTS.md).

## Repository layout

| Directory | Purpose |
| --- | --- |
| `sa_agent/` | Runner, configuration, agent adapters, navigation, evaluators and recording |
| `src/` | Win32 Plugin-SDK ASI and fixed-width shared-memory protocols |
| `reader/` | Basic read-only telemetry and optional localhost HTTP endpoint |
| `tasks/` | Five current definitions; historical parking/wanted tasks in `legacy/` |
| `configs/` | Public defaults, render profiles and ignored local overrides |
| `schemas/` | Task and result JSON contracts for tooling |
| `tests/` | Offline tests, native movement projection and kill attribution checks |
| `tools/` | Build, installation, diagnostics and repository validation |
| `docs/` | Setup, architecture, extension guides and methodology |
| `runs/` | Ignored local results, traces and videos |

## License and attribution

Original repository code is [MIT licensed](LICENSE). GTA assets and third-party
dependencies are separate; see [third-party notices](THIRD_PARTY_NOTICES.md).
This community project is unaffiliated with Rockstar Games.
