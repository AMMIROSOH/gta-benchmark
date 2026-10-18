# Commands and configuration

Use `python -m sa_agent` from the repository root, or an installed
`gta-benchmark` / `sa-bench` entry point. The commands below show module usage.
Use `D:\SA-Agent\venv\Scripts\python.exe` for the local game runtime.

## Commands

| Command | Behavior | Game / network access |
| --- | --- | --- |
| `--version` | Print benchmark version | None |
| `list` | Show the five sample task definitions | None |
| `agents` | List registered provider adapters | None |
| `validate` | Validate config and all task definitions | None |
| `profile` | Generate the two render-profile INIs | Local files only |
| `state` | Read player, world and navigation state | Read-only game access |
| `reset` | Start New Game and wait for the opening state | Launch/install/reset as configured; no model |
| `run TASK` | Prepare, record, evaluate and finalize an attempt | Real gameplay and configured model requests |
| `results` | List stored terminal results | Local files only |

```powershell
python -m sa_agent run steal_car --reset new_game --timeout-seconds 120
python -m sa_agent run tasks/02_walk_to_waypoint.json --reset none
python -m sa_agent run steal_car --model jev-1.14.0 --post-success-seconds 20
python -m sa_agent state --summary
python -m sa_agent state --watch
python -m sa_agent reset
python -m sa_agent results
```

`run` also accepts `--config PATH`, `--output-dir PATH` and `--decision-hz 5|10`.
`reset`, `profile` and `validate` accept `--config PATH`. `results` and `reset`
accept an output directory. See each command's `--help` for its exact arguments.

`run` exits 0 on overall success, 1 on a recorded failed attempt, and 2 on a CLI
or configuration error. Ctrl+C during a task records a failed cancellation;
Ctrl+C during aftermath recording preserves the frozen task verdict and ends
the tail. A preparation-only command interrupted by Ctrl+C exits 130.

## Configuration selection

Selection order is explicit `--config`, then `configs/benchmark.local.json` if
present, then tracked `configs/benchmark.json`. The local file is a **complete
config**, copied from the defaults; files are not merged. Commands snapshot the
effective config in the run directory. Relative output paths resolve from the
repository root.

`config.local.json` is separate: it tells native build/install tools where the
game, SDK and installed Windows SDK live. It is based on `config.example.json`.

| Section | Key | Meaning / default |
| --- | --- | --- |
| `agent` | `name`, `model` | Adapter `jev`, requested model `jev-1.14.0` |
| | `endpoint` | Official TypeSafe systemone endpoint for the Jev adapter |
| | `api_key_env` | Environment variable name, `TYPESAFE_API_KEY` |
| | `proxy` | `null` or a loopback HTTP/HTTPS/SOCKS proxy; local override may set V2Ray |
| | `decision_hz` | 5 or 10; a ceiling for primitive choices |
| | `request_timeout_seconds` | 10-second model request deadline |
| | `max_decision_age_seconds` | Drop responses older than 2.5 seconds |
| | `max_consecutive_errors` | Fail after 3 consecutive request/response errors |
| | `minimum_confidence` | Below this threshold, choose idle / no target |
| | `history_size` | Last 8 decisions/selections in model context |
| `game` | `width`, `height`, `fps_cap` | 1280 × 720 and 30 FPS |
| | `telemetry_max_age_ms` | Maximum accepted age, 750 ms |
| | `connection_grace_seconds` | 3 seconds for loss of foreground/fresh state |
| | `pause_grace_seconds` | 10 seconds for paused gameplay |
| | `action_duration_ms` | 200 ms; native maximum 750 ms |
| | `startup_countdown_seconds` | 5 seconds before task staging/recording |
| `recording` | `fps`, `width`, `height` | Constant 30 FPS at the game dimensions |
| | `ffmpeg`, `encoder` | Executable or PATH name; `libx264` |
| | `crf`, `preset` | Encoder quality/speed, 20 / `veryfast` |
| | `device_index`, `output_index` | DXGI device/output, both 0 |
| | `monitor_origin_xy` | Optional desktop origin for that monitor, defaults to `[0, 0]` |
| | `max_backlog_seconds` | Fail if encoder falls more than 2 seconds behind |
| | `post_success_seconds` | 15 seconds of extra footage; 0 disables, maximum 120 |
| | `audio` | Silent recordings; keep false |
| `reset` | `mode` | `new_game` or `none` |
| | `executable` | Actual installed `gta_sa.exe`; edit your local copy |
| | `launch_if_missing` | Launch an absent game, true |
| | `install_bridge_if_closed` | Install the built ASI before an automatic launch, true |
| | `launch_timeout_seconds` | Wait up to 60 seconds for the bridge/menu |
| | `timeout_seconds` | Preparation deadline, 180 seconds; separate from task time |
| | `skip_intro` | Use normal cutscene skipping during preparation |
| | `settle_seconds` | Verify the opening state for 2 seconds after native stability |
| | `start_position`, `start_radius_m` | Readiness region near `(2235, -1265, 24)`, radius 60 m |
| | `require_starting_bicycle`, `bicycle_radius_m` | Require a BMX within 30 m |
| root | `output_dir` | `runs` |

The car controller runs on a 10 Hz schedule independently of Jev. It requests
target selection when necessary, at most once every two seconds. Changing
`decision_hz` does not alter this schedule, video FPS or the task deadline.

## Credentials and proxy

Inline `api_key`, `key`, `token` and `authorization` fields are rejected in the
agent config. `.env.local` is ignored and the loader reads only the expected
TypeSafe key. Environment values win. Credentials are passed to Windows curl
through stdin, without redirects or command-line key arguments.

The loopback proxy applies only to the adapter's requests and the connectivity
check. It does not modify Windows proxy settings. For SOCKS, `socks5h` also
resolves DNS through the proxy. Run `python tools/check_jev.py --config PATH`
only when you want an authenticated network check.
