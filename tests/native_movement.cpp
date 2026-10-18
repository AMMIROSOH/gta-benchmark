#include "../src/movement.h"
#include <cmath>
#include <cstdio>
#include <initializer_list>

// Reconstruct the game's GetRadianAngleBetweenPoints branch logic and
// CTaskSimplePlayerOnFoot camera rotation, rather than round-tripping the
// projection with its own inverse implementation.
float GameHeading(short stick_x, short stick_y, float camera) {
    float x = -static_cast<float>(stick_x), y = static_cast<float>(stick_y);
    if (y == 0) y = 0.0001f;
    constexpr float pi = 3.14159265358979323846f;
    const auto raw = x > 0 ? (y > 0 ? pi-std::atan2(x/y, 1.0f) : -std::atan2(x/y, 1.0f)) :
                            (y > 0 ? -(pi+std::atan2(x/y, 1.0f)) : -std::atan2(x/y, 1.0f));
    return raw-camera;
}
int main() {
    constexpr float pi = 3.14159265358979323846f;
    for (float magnitude : {60.0f, 128.0f}) {
        for (int camera = -16; camera <= 16; ++camera) for (int direction = -16; direction <= 16; ++direction) {
            const float h = direction*pi/8, c = camera*pi/8;
            const auto stick = sa_agent::WorldDirectionToStick(-std::sin(h), std::cos(h), c, magnitude);
            const float actual = GameHeading(stick.x, stick.y, c);
            const auto error = std::abs(std::atan2(std::sin(actual-h), std::cos(actual-h)));
            if (error > 0.02f || std::abs(stick.x) > 128 || std::abs(stick.y) > 128) {
                std::fprintf(stderr, "Incorrect world direction at camera=%f heading=%f error=%f\n", c,h,error);
                return 1;
            }
        }
    }
    const auto stopped = sa_agent::WorldDirectionToStick(0,0,pi,128);
    return stopped.x || stopped.y ? 1 : 0;
}
