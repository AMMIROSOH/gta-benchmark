#pragma once

namespace sa_agent::lifecycle {
void Initialize();
void Tick(); // Called on the game thread after the normal pad update, including menus.
bool Busy();
void Shutdown();
}
