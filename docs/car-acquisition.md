# State-based car acquisition

`steal_car` uses a hybrid policy introduced in version 2. Jev selects a specific automobile
from typed options. The local controller executes its route and interaction at
10 Hz using fresh structured game data. This division is recorded as
`policy_mode=target_selection_with_road_controller` in new results; it is
not an evaluation of Jev choosing every individual key press.

1. Filter vehicles by actual subclass, health, openable locks, usable driver door,
   elevation, traffic speed and a reachable route. Bicycles and motorcycles are
   reported as other vehicles but are not valid targets for stealing a car.
2. Ask Jev to choose a vehicle pool reference, with route cost and the proposed
   approach strategy attached to each option. Keep that target until acquired,
   unavailable, or blocked. Nearby cars changing order does not change the target.
3. Prefer native road links and clear pedestrian connections. Route around
   geometry and the car's rotated collision footprint instead of walking through
   the hood. A clear short final approach can leave the road to reach the door.
4. For slow moving traffic, approach a point in front of the car and wait for it
   to stop. Then go around the vehicle to the driver side. Fast traffic that
   cannot reasonably be intercepted is rejected. Parked cars go directly to the
   driver-side approach.
5. Slow down near the real front-left door, obtained from
   `CCarEnterExit::GetPositionToOpenCarDoor(..., 10)`. Press enter/F once only when
   near that door and the car is stopped and usable. Wait for the game's entry
   task to finish instead of repeatedly toggling enter/exit. Once seated, release
   inputs and let the evaluator measure the two-second driver hold.

The controller uses 16 world-relative clearance probes, vehicle collision-box
dimensions, forward/right vectors, velocity, road/pedestrian links, and a flag
for an active entry task. It replans when progress stalls and temporarily rejects
a failed target. If no suitable car is available, it moves to one clear nearby
road observation point and waits instead of choosing random movement keys.
Version 3 permits an on-foot outdoor start without a car already in range and
allows a clear connection to a road or sidewalk node across a longer alley.

World-coordinate movement still produces normal gamepad input. The native bridge
converts the desired direction using the game's camera orientation on each
frame. It does not teleport CJ, assign a native enter-car task, spawn cars, change
traffic AI or unlock vehicles. A driver may refuse to stop; blocked routes and
unsuitable traffic remain real task limitations.

Jev receives a compact candidate summary, not the full navigation graph or any
frames. Local navigation continues while the API is busy. Model selection is
retried at most every two seconds while a target is needed. Result logs separate
`jev_target_selection` entries from `navigation_controller` control ticks and
include the target, phase, waypoint, reason and input acknowledgement.

## Verification

```powershell
rtk proxy D:\SA-Agent\venv\Scripts\python.exe -m sa_agent state --summary
rtk proxy D:\SA-Agent\venv\Scripts\python.exe -m unittest discover -s tests -v
rtk proxy D:\SA-Agent\venv\Scripts\python.exe tools\build.py
rtk proxy ctest --test-dir build -C Release --output-on-failure
```

The summary labels cars, motorcycles and bicycles separately and shows actual
driver-door positions, loaded road/pedestrian node counts and navigation freshness.

The offline tests cover vehicle filtering, persistent target references, native
road-link routing, rotated vehicle detours, traffic interception, one-shot entry,
waiting through animations, and closed-loop convergence to a door. The native
test checks the actual world-direction projection against the game's movement
formula over different camera angles. These checks do not by themselves prove
that a live game run will succeed.

Older artifacts use the `jev_target_selection_with_road_controller` label.
See [results and methodology](results.md) before combining them with new runs.
