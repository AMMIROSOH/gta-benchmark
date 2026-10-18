# Read-only telemetry tools

The basic telemetry reader uses Python's standard library on Windows. Its
160-byte mapping is also composed into the full `GameClient` state. For nearby
vehicles and navigation data, use `python -m sa_agent state --summary`.

```powershell
rtk proxy python reader\sa_telemetry.py --once
rtk proxy python reader\sa_telemetry.py --watch --interval 0.5
rtk proxy python tools\reader_service.py start
rtk proxy python tools\reader_service.py status
rtk proxy python tools\reader_service.py stop
```

The optional hidden reader serves `http://127.0.0.1:8765/state` and `/health`.
It is not a Windows service and is not added to startup. The task runner reads
shared memory directly and does not require this HTTP service.

Check `live` and `sample_age_ms` before acting. `waiting_for_game` means no samples
have arrived; `stale` means sampling stopped more than two seconds ago. A fresh
`paused` snapshot does not prove the simulation is advancing. Basic player data
can remain visible as last-known values after sampling stops.

`python tools/verify_live.py --connection-only` performs a read-only multi-sample
check and writes reports under ignored `runtime/`. Omit `--connection-only` to
also require the game clock to advance. These commands access the real game and
are separate from offline tests.

The SDK and game paths come from `config.local.json`. The ASI installs under
`<game_dir>/scripts/SAAgentTelemetry.asi` and writes its log beside the plugin.
Build and reader logs are under `logs/`; installation manifests under `runtime/`
preserve the SDK revision and deployed file hashes. See [setup](setup.md) and
[bridge contract](bridge.md).
