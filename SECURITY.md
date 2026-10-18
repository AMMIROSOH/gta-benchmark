# Credentials and sensitive reports

Keep API keys in environment variables or ignored `.env.local`. Use a complete
ignored `configs/benchmark.local.json` for machine-specific settings. Run outputs
can include local paths and game-state traces; review artifacts before sharing.

Report credential exposure or a native/control-channel vulnerability privately
to the maintainer through the channel where you obtained this repository.
Provide a redacted reproduction and affected source revision. Do not include a
live key, memory dump or unrelated personal data in a public issue.

The optional telemetry HTTP reader binds to localhost and is read-only. It is
not needed by the task runner. Native reset and input channels are local and
process-owned; model adapters should never gain direct access to them.
