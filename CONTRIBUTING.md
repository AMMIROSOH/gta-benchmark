# Contributing

GTA Benchmark is a state-driven agent evaluation project, initially for classic
San Andreas 1.0 US. Keep task rules, provider adapters, shared execution and
environment preparation separate so comparisons remain understandable.

## Development checks

Python 3.11+ can run the offline core without installing capture dependencies:

```powershell
python tools/check_repo.py
python -m unittest discover -s tests -v
python -m sa_agent validate --config configs/benchmark.json
```

On a configured Windows machine, build native changes with the existing MSVC
toolchain and run the movement test:

```powershell
python tools/build.py
ctest --test-dir build -C Release --output-on-failure
```

These checks do not launch GTA or call Jev. Live gameplay, DXGI recording and
authenticated connectivity checks are separate, intentional operations. Preserve
the user's open game and local results during ordinary development.

## Making changes

- For tasks, follow [task authoring](docs/adding-tasks.md), including versioning,
  strict preconditions and tests against false-positive completion.
- For providers, follow [agent authoring](docs/adding-agents.md). Mock transports
  in tests and keep actual model identity/usage truthful.
- For native changes, keep layouts fixed-width and pointer-free. Update both
  C++ and Python sides plus the [bridge contract](docs/bridge.md). Version the
  mapping when its layout changes; preserve command leases and ownership checks.
- For execution changes, record the controller mode/version and explain whether
  historical results remain comparable.
- For result changes, update [result schema](schemas/result.schema.json),
  [methodology](docs/results.md) and provenance tests. Preserve old artifacts.
- For documentation, update the relevant guide and its index links. Keep local
  machine history out of the landing README.

Use focused changes with a clear problem, resulting behavior and validation.
Fix source errors before claiming a build passed. A passing offline test is not
evidence of a successful real game task. Report live evidence with its task,
model, controller, configuration, result and finalized video.

## Local files and dependencies

`config.local.json`, `configs/*.local.json`, `.env.local`, `runs/`, `logs/`,
`runtime/` and `build/` stay local. Do not commit credentials, game assets,
downloaded dependencies, ASIs, executable dumps or recordings. Existing artifacts
must not be deleted merely to make Git status clean.

Dependency/runtime downloads and backups use `D:\SA-Agent` in the current
Windows tooling. Do not install a C++ toolchain as part of repo checks. Keep
third-party attribution in [notices](THIRD_PARTY_NOTICES.md) when adding an
integration. Contributions to original repo code use the [MIT license](LICENSE).
