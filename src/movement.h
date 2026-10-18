#pragma once
#include <cmath>

namespace sa_agent {
struct StickDirection { short x, y; };
inline StickDirection WorldDirectionToStick(float dx, float dy, float camera_orientation, float magnitude) {
    if (dx == 0 && dy == 0) return {};
    const float angle = std::atan2(-dx, dy) + camera_orientation;
    return {static_cast<short>(std::lround(-std::sin(angle)*magnitude)),
            static_cast<short>(std::lround(-std::cos(angle)*magnitude))};
}
}
