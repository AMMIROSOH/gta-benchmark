# Validation and current limitations

The repository is an experimental benchmark foundation. Offline tests establish
specific contracts; live recordings establish what happened in individual
attempts. Neither alone establishes a model-wide success rate.

## Recorded integration evidence

On 2026-10-18, `steal_car` version 3 with `jev-1.14.0` and the shared road/door
controller succeeded in **29.30 seconds** within a 120-second limit. The selected
vehicle reference was 12033, model 554; final telemetry matched that vehicle and
confirmed the driver role for 2.03 seconds. There was one enter/F pulse, no API
errors and no native sampling errors. The 1280×720 H.264 video contained 879
frames at constant 30 FPS and decoded completely without errors.

That local artifact directory is
`runs/steal_car/20261018T170731-c70911dd/`. Artifacts are retained locally and are
not bundled with the source. This run used a stopped car and predates the New
Game/aftermath extensions and provenance schema. Moving-traffic interception was
not exercised in that live success. The other four sample policies have no
verified live results recorded here.

Earlier primitive-policy attempts failed due to direct-route API timeouts and,
after a working proxy route, a task timeout. Those older policies/modes are not
equivalent to the current assisted car-selection baseline. Their results remain
in their original local directories rather than being rewritten as current runs.

## Offline coverage

The tests cover navigation candidate filtering, stable vehicle references,
road routing, rotated-car detours, bounded traffic waits, one-shot entry,
animation handling and simulated convergence. Contract tests also cover task
validation, false-positive driver/bicycle cases, hold freshness, distance
discontinuities, local config selection and reproducibility fingerprints.
Windows-only orchestration tests mock every game/model/capture operation and
verify frozen success timing, aftermath interruption, host reset acknowledgement
and rejection of an old session generation. They never connect to a live game.

The portable C++ movement test checks the bridge's world-direction projection
against an independently reconstructed game movement formula across camera
angles. Full native sampling, renderer hooks, DXGI capture, model connectivity
and New Game behavior need separate checks in the supported installed game.
The standard offline suite and CI do not launch GTA or call a model.

## Limits to account for

- The planned `kill_npc` and `earn_money` replacements are documentation only.
  Verified kill attribution, fixed-window numeric scoring and the replacement
  task definitions are not implemented or live-validated; see [task pack](task-pack.md).
- Only classic GTA SA 1.0 US is supported by the inspected hooks and structures.
- Nearby entities, loaded road nodes and local probes are bounded; there is no
  global route map or complete world perception.
- Car acquisition shares a local navigation controller across model selections.
- Traffic may refuse to stop, paths may be blocked, and native entry can fail.
- New Game does not seed identical traffic or stage the other task scenarios.
- The driver-seat rule does not infer legal ownership or prove a carjacking.
- Target rates are schedules; actual API/control rates vary and are logged.
- CFR video can contain duplicates; recording is silent and window-position sensitive.
- DXcam 0.3.0 has a known local COM cleanup warning; artifact integrity must be
  checked from finalization/error data and, for published evidence, the video.

Use [results and methodology](results.md) when reporting comparisons and the
[roadmap](roadmap.md) for the next development steps.
