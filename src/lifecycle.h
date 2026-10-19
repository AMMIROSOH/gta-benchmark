#pragma once
#include <cstdint>

namespace sa_agent::lifecycle {
void Initialize();
void Tick(); // Called on the game thread after the normal pad update, including menus.
bool Busy();
std::uint32_t Generation();
void Shutdown();
}
