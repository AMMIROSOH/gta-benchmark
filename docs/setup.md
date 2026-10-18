# Windows setup

Run commands from the repository root. A local runtime uses `D:\SA-Agent` for
dependencies, downloads, caches, backups and its Python virtual environment.
Code, configuration, logs and run outputs remain in the `gta-benchmark` checkout.
The distribution name is `gta-benchmark`; imports and module commands continue
to use `sa_agent`. Existing `D:\SA-Agent` runtime paths and native binary names
are retained for compatibility.

## Prerequisites

| Component | Requirement |
| --- | --- |
| Game | A separately installed classic GTA San Andreas 1.0 US, x86 |
| OS | Windows with a visible game window for DXGI recording |
| Python | Python 3.12 for the recorded baseline; offline core supports 3.11+ |
| Build tools | Existing Visual Studio 2022 C++ tools, Win32 target, Windows SDK and CMake 3.20+ |
| ASI loader | Existing recognized Ultimate ASI Loader as `vorbisFile.dll` |
| Plugin-SDK | Separate checkout pinned to the revision below |
| Video encoder | Installed FFmpeg with `libx264`, or bootstrap's checksummed download |
| Agent | TypeSafe API key for Jev; an optional local proxy can be configured |

The tools do not install or update a C++ toolchain, patch the game executable or
download GTA assets. The installer rejects unsupported executables and loaders.
Use `python tools/inspect_game.py --help` to inspect its available arguments.

## Local settings

```powershell
Copy-Item config.example.json config.local.json
Copy-Item configs/benchmark.json configs/benchmark.local.json
Copy-Item .env.example .env.local
```

Edit `config.local.json` with the actual game directory, Plugin-SDK directory
and your installed Windows SDK version. The example SDK version is
`10.0.22000.0`; use the version already available on your machine.

Edit `configs/benchmark.local.json`:

- Set `reset.executable` to that same game's `gta_sa.exe`.
- Set `recording.ffmpeg` to your installed executable, or keep `ffmpeg` if on PATH.
- Set `agent.proxy` to `null` for direct HTTPS or your local listener, for example
  `socks5h://127.0.0.1:10808`. Proxy failures do not fall back to a direct route.
- Select the correct DXGI `device_index` and `output_index` for recording.

Put the TypeSafe key in `.env.local` or `TYPESAFE_API_KEY` in your environment.
Environment values take precedence. Local settings, credentials, installed
binaries and run artifacts are excluded from Git.

## Python runtime and FFmpeg

```powershell
py -3.12 tools/bootstrap.py --skip-ffmpeg
```

This creates `D:\SA-Agent\venv` and installs the package in editable mode.
Use this checkout/editable installation workflow: task data, configs and native
tools are repository files, so a standalone wheel without the checkout is not
currently a supported installation mode.
Omit `--skip-ffmpeg` when FFmpeg is absent and you want bootstrap to download a
publisher-checksummed build to D:. An existing configured FFmpeg is reused.
Bootstrap does not launch GTA or call a model.

For an exact copy of the recorded Python dependencies, install
`requirements-runtime.txt` with the virtual environment's Python. The pinned
baseline uses NumPy 2.5.4, DXcam 0.3.0 and comtypes 1.4.17 on Python 3.12.
The general package dependency range also permits other NumPy 1.26–2.x versions;
run manifests record what was actually installed.

## Plugin-SDK and native build

For a new machine, obtain the official SDK separately:

```powershell
git clone --recurse-submodules https://github.com/DK22Pac/plugin-sdk.git D:\SA-Agent\dependencies\plugin-sdk
git -C D:\SA-Agent\dependencies\plugin-sdk checkout 15f15b60bbf74c106e1b496ff92c98764abf4605
git -C D:\SA-Agent\dependencies\plugin-sdk submodule update --init --recursive
```

Close GTA completely before deployment, then run:

```powershell
D:\SA-Agent\venv\Scripts\python.exe -m sa_agent profile
python tools/build.py
python tools/install.py
python tools/setup_windowed.py
```

`build.py` uses `config.local.json`, generates the SDK project if needed, builds
its release library and builds the ASI for Win32. `install.py` rejects a binary
older than the source and backs up replaced ASI/INI files on D:. It preserves
the game executable, loader and existing SilentPatch.

`setup_windowed.py` downloads the pinned official Windowed Mode v2.2 archive,
checks SHA-256, and installs its ASI and configured window profile. The profile
command generates both INIs. A full game exit/relaunch loads updated ASIs.

## First use

```powershell
D:\SA-Agent\venv\Scripts\python.exe -m sa_agent validate
D:\SA-Agent\venv\Scripts\python.exe tools/check_jev.py
D:\SA-Agent\venv\Scripts\python.exe -m sa_agent run steal_car --reset new_game
```

`validate` is offline. `check_jev.py` makes one authenticated models request using
the configured route. `run` launches/prepares GTA and evaluates a real task.
Keep the game visible, foreground and stationary while recording.

With default reset settings, an absent game triggers installation of the already
built ASI before launch. A game running an old plugin must exit once first.
Later runs can reset through New Game without restarting the executable.

For other task starting states, use manual staging and `--reset none`. See
[episode lifecycle](episode-lifecycle.md) and [troubleshooting](troubleshooting.md).
