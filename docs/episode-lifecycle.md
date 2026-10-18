# Episode preparation and aftermath recording

The default benchmark config now prepares a **fresh New Game before every run**
and records **15 seconds after success**. Preparation and recording are separate
from the scored task clock. The previously successful 29.30-second recording
predates these extensions; see [validation](validation.md) for evidence and limits.

## Starting from the opening alley

```powershell
# Prepare New Game only; no Jev request, task attempt or recording.
rtk proxy D:\SA-Agent\venv\Scripts\python.exe -m sa_agent reset

# Reset first, run the task, then record 15 seconds of aftermath on success.
rtk proxy D:\SA-Agent\venv\Scripts\python.exe -m sa_agent run steal_car

# Use an already staged game without resetting it.
rtk proxy D:\SA-Agent\venv\Scripts\python.exe -m sa_agent run drive_100m --reset none
```

The reset extension requires the new ASI. If GTA is running an older bridge,
close the game once before using `reset` or the default `run`. With
`reset.install_bridge_if_closed=true`, the command invokes the existing installer
before launching an absent game. The installer checks source freshness, creates
backups, and preserves the executable and existing mods. A running game is never
killed to deploy the bridge. `reset.launch_if_missing=false` disables launching;
`reset.install_bridge_if_closed=false` disables automatic installation.

If a run reports `reset_failed` with zero elapsed time and no video, read the
`error` printed in its CLI JSON (also saved in `result.json`). A missing New Game
bridge means the running game has not loaded the reset extension. Fully exit
GTA to the desktop once and rerun the same command while it is closed. Choosing
New Game inside the menu does not reload an ASI. The configured automatic
installer runs only when the game process is absent.

Preparation follows these steps:

1. Locate the configured game or launch it if absent. Wait for the lifecycle
   mapping and a usable game window, including the initial main menu.
2. Acquire the same exclusive control mutex used by task runs and release any
   injected inputs. Send one acknowledged New Game request to the native bridge.
3. On the game thread, call the normal front-end
   `CMenuManager::DoSettingsBeforeStartingAGame()` path with mission packs and
   saved-game loading disabled. GTA's outer loop performs its own shutdown and
   reinitialization. The bridge does not directly call world initialization from
   a gameplay callback.
4. Require a new initialization generation before accepting any ready state.
   During preparation only, skip active opening cutscenes with the standard
   `CCutsceneMgr::SkipCutscene()` function. Let the game's script finish cleanup.
5. Wait for living CJ with controls enabled, no menu/cutscene/fade, then require
   fresh on-foot outdoor telemetry near `(2235, -1265, 24)`, zero wanted stars,
   and a BMX (model 481) within 30 metres. The native controllable state must
   last three seconds; the host validates the opening state for two more seconds,
   then sends a completion acknowledgement. Gaps between opening scenes cannot
   end preparation solely because player controls briefly become available.
6. Check the task's own preconditions, start recording, and only then start the
   task clock and agent decisions.

The position is a readiness check, not a teleport destination. No save is loaded,
written or deleted. New Game discards the current **unsaved** session just as the
menu command does. Traffic and pedestrians are not seeded, so repetitions have
the same story starting point but may differ in nearby traffic.

Preparation has a separate 180-second deadline and no Jev actions. Missing
acknowledgement, stale/wrong-session data, exit, native failure or an unexpected
start produces `reset_failed` before the task starts. The standalone command
writes `runtime/resets/<id>/reset.json` and `reset_events.jsonl`; task preparation
writes them in the run directory. Cancellation ends intro skipping; a New Game
transition already committed by GTA cannot be undone. Ordinary task actions
cannot invoke resets, and the bridge ignores ordinary task input while resetting.

The driving, parking and wanted-level samples still require their documented
starting conditions. A fresh on-foot game does not satisfy them. Use
`--reset none` with a staged scenario for those tasks; reset does not spawn a car,
put CJ in one, award wanted stars or claim the scenario is ready.

## Recording after success

`recording.post_success_seconds` defaults to 15 and can be overridden per run:

```powershell
rtk proxy D:\SA-Agent\venv\Scripts\python.exe -m sa_agent run steal_car --post-success-seconds 20
```

Use 0 to disable the extra footage. Values must be finite and between 0 and 120.
The same 1280×720 constant-30-FPS MP4 continues after success. At the terminal
task verdict the runner freezes `elapsed_seconds`, `finished_at_utc`,
`task_status`, `task_reason`, task progress and `final_state`. Agent input is
released and no new decisions are requested. The game continues naturally;
there is no automatic driving after entering the car. The ownership mutex stays
held through video finalization so another runner cannot reset the game mid-video.

For example, success at 29.30 seconds with a 15-second tail produces roughly
44.30 seconds of footage, while task time remains 29.30 seconds. Recording startup
may contribute a small leading offset; `video.task_start_seconds` and
`video.task_end_seconds` locate the task within the file. `post_success_recording`
reports the requested/actual duration, completion or interruption, and the last
aftermath state. Additional telemetry goes to `post_success_observations.jsonl`.

The 120-second task deadline does not truncate a successful tail. Failed tasks
do not get one. Pause, focus loss or telemetry loss beyond the connection grace
ends the tail with an explicit interruption reason; Ctrl+C ends it as cancelled.
Neither changes the frozen task verdict. Video encoding/cleanup errors still
make the overall run `failed`, while `task_status` preserves the goal outcome.
`artifacts_finished_at_utc` records when the video and cleanup finish.

## Native contract and references

The reset command uses a 64-byte `Local\SAAgent.Reset.v1` mapping, and lifecycle
status uses a 96-byte `Local\SAAgent.Lifecycle.v1` mapping. They have fixed-width,
4-byte-packed fields and the same sequence-counter protocol as game telemetry.
Commands include a target PID, live owner PID, nonzero request ID, a maximum
five-second acceptance lease and a bounded preparation timeout. Accepted requests
are deduplicated by owner/request ID. A dead owner cancels further preparation.

The front-end and cutscene behavior follows the primary reverse-engineered
sources: [New Game settings](https://github.com/gta-reversed/gta-reversed/blob/master/source/game_sa/MenuManager.cpp),
[outer game loop](https://github.com/gta-reversed/gta-reversed/blob/master/source/app/platform/win/WinMain.cpp),
and [cutscene skip](https://github.com/gta-reversed/gta-reversed/blob/master/source/game_sa/CutsceneMgr.cpp).
The SDK declarations come from the pinned local Plugin-SDK checkout.
