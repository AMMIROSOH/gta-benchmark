#pragma once
#include "agent_protocol.h"
namespace sa_agent::navigation {
void Initialize();
void Publish(const WorldSnapshot& world);
}
