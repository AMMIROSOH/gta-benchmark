#pragma once

namespace sa_agent::bridge {
void Initialize();
void PublishWorld();
void Shutdown();
unsigned int TelemetryIntervalMilliseconds();
}
