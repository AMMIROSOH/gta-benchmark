# Changelog

## Unreleased — 0.1.0 foundation

- Standardized the project/repository and distribution name as `gta-benchmark`,
  retaining compatible Python imports, CLI aliases and native bridge names.
- Documented planned replacements of `park_and_exit` with `kill_npc` and
  `lose_wanted` with `earn_money`: maximize kill count or net cash over a fixed
  120-second window. Task/runtime implementation remains unchanged.
- Established GTA Benchmark documentation, MIT licensing and contribution guides.
- Added classic SA state/navigation/control and host New Game bridge.
- Added Jev target selection with shared car acquisition and primitive-action samples.
- Added five versioned task contracts with deterministic host evaluation.
- Added constant-30-FPS recordings, success aftermath and independent task timing.
- Added source/config/task provenance, result schema and explicit controller modes.
- Separated portable defaults from ignored local settings.
- Added offline contract tests, repository validation and GitHub Actions checks.
- Removed the one-off sampling debugger and duplicate game-launch script.

No hosted release or model leaderboard is published by this initialization.
