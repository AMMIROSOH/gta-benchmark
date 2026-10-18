# Troubleshooting

Start with the CLI's `error` and the saved `result.json`. For preparation issues,
also inspect `reset.json` and `reset_events.jsonl`. For recording issues, inspect
`video.error` and `ffmpeg.log`. These files stay under ignored local directories.

| Symptom | Cause / action |
| --- | --- |
| `reset_failed`, 0 seconds, missing New Game bridge | Fully exit GTA once; rerun the same command while it is closed so the built ASI installs before launch. New Game inside the menu does not reload an ASI. |
| Installer says ASI predates sources | Run `python tools/build.py`, then install with GTA closed. |
| Installer reports unsupported EXE or loader | Inspect your installation/config. The bridge targets classic 1.0 US and the currently recognized loader layout. |
| Game/SDK path wrong after cloning | Edit ignored `config.local.json` and `configs/benchmark.local.json`; the public game path is an example. |
| TypeSafe key missing | Set `TYPESAFE_API_KEY` or ignored `.env.local`. Keep real keys out of JSON config. |
| TypeSafe HTTP 451 | The selected network route is unavailable to the service. The local baseline uses a configured loopback V2Ray proxy; inspect `agent.proxy` and its listener. |
| Proxy error | Start/fix that local listener or explicitly select a direct route if usable. Requests never silently fall back to direct HTTPS. |
| `preconditions_failed` | Read `precondition_failures`. Fresh New Game is on foot with zero stars; driving/wanted samples need staging and `--reset none`. |
| Reset times out in the intro | Keep GTA foreground and inspect native phase, generation, cutscene flags and last state. The host must validate the opening alley and BMX before completion. |
| Game says paused / stale | Resume gameplay and keep the window foreground. A visible player snapshot can be old; check `live` and sample ages. |
| Another runner owns controls | Finish/cancel that run, including its aftermath/finalization. Ownership remains held until the video is closed. |
| Render profile mismatch | Generate profiles, install with GTA closed, and relaunch. Select a supported resolution. |
| No captured game frames | Check foreground, DXGI device/output and monitor origin. Keep the window visible and stationary. |
| Window moved or resized | Recording deliberately stops; stage the window before the next attempt. |
| Encoder cannot maintain rate | Inspect encoder settings/output disk and backlog; record the settings used for any comparison. |
| DXcam COM cleanup warning | The recorded local DXcam 0.3.0 baseline emitted this warning even when MP4 finalization and full decoding succeeded. Check the actual video/error instead of assuming it is valid or invalid. |

## Read-only game diagnostics

These commands read the game but do not send controls:

```powershell
python -m sa_agent state --summary
python reader/sa_telemetry.py --once
python tools/verify_live.py --connection-only
```

`verify_live.py` samples for several seconds and writes a local diagnostic report.
It is outside the offline test suite. `python tools/check_jev.py` is likewise an
explicit authenticated network check, separate from a task attempt.

The ASI writes `SAAgentTelemetry.log` beside its installed binary. Native build
logs are under `logs/`; installation manifests and backups identify the exact
files deployed. A loaded ASI can only be replaced after the game process exits.
