"""State-only car acquisition: Jev chooses a car; this controller executes the route."""

from dataclasses import dataclass
import heapq
import math


def distance(a, b):
    return math.hypot(a["x"]-b["x"], a["y"]-b["y"])


def vehicle_map(state):
    geometry = {g["reference"]: g for g in state["navigation"]["vehicles"]}
    return {v["reference"]: {**v, **geometry[v["reference"]]}
            for v in state["world"]["nearby_vehicles"] if v["reference"] in geometry}


def door_goal(car):
    door, right = car["driver_door"], car["right_xy"]
    return {**door, "x": door["x"]-right["x"]*0.3, "y": door["y"]-right["y"]*0.3}


def road_route(state, car, front=False):
    """Dijkstra over loaded, geometry-checked native road/pedestrian links."""
    position = state["player"]["position"]
    goal = car["front_stop"] if front else door_goal(car)
    direct = car["front_clear"] if front else car["door_clear"]
    if direct and distance(position, goal) < 8:
        return [goal], distance(position, goal)
    nodes = {n["reference"]: n for n in state["navigation"]["nodes"]}
    ends = set(car["front_anchors"] if front else car["door_anchors"])
    costs, parents, queue = {}, {}, []
    for ref, node in nodes.items():
        d = distance(position, node["position"])
        # Native visibility is the geometric check. The first sidewalk node
        # can be 20-40 m away in an alley; a short distance cutoff strands CJ.
        if node["visible"] and d <= 90:
            costs[ref] = d*1.4
            parents[ref] = None
            heapq.heappush(queue, (costs[ref], ref))
    best, best_cost = None, math.inf
    while queue:
        cost, ref = heapq.heappop(queue)
        if cost != costs[ref] or cost >= best_cost:
            continue
        node = nodes[ref]
        if ref in ends:
            total = cost + distance(node["position"], goal)*1.4
            if total < best_cost:
                best, best_cost = ref, total
        for link in node["links"]:
            other = nodes.get(link)
            if not other or abs(node["position"]["z"]-other["position"]["z"]) > 2:
                continue
            weight = 0.8 if node["road"] and other["road"] else 1.05
            candidate = cost + distance(node["position"], other["position"])*weight
            if candidate < costs.get(link, math.inf):
                costs[link], parents[link] = candidate, ref
                heapq.heappush(queue, (candidate, link))
    if best is not None:
        route = [goal]
        while best is not None:
            route.append(nodes[best]["position"])
            best = parents[best]
        route.reverse()
        return route, best_cost
    if direct:
        return [goal], distance(position, goal)*1.6
    return [], math.inf


def candidate_cars(state, excluded=()):
    candidates = []
    player = state["player"]["position"]
    for car in vehicle_map(state).values():
        if (car["reference"] in excluded or not car["is_automobile"] or
                not car["driver_door_valid"] or not car["openable"] or car["door_busy"] or
                car["health"] <= 300 or abs(car["position"]["z"]-player["z"]) > 3):
            continue
        moving = car["speed_mps"] > 0.7
        forward = car["forward_xy"]
        ahead = sum((player[a]-car["position"][a])*forward[a] for a in ("x", "y"))
        # Do not chase fast traffic from behind or walk into a high-speed lane.
        if car["speed_mps"] > 4.0 or (car["speed_mps"] > 2.0 and ahead < car["front_extent"]+2):
            continue
        route, cost = road_route(state, car, front=moving)
        if not route:
            continue
        candidates.append({"reference": car["reference"], "model_id": car["model_id"],
            "kind": "automobile", "occupied": car["occupied"], "speed_mps": car["speed_mps"],
            "distance_m": distance(player, car["position"]), "route_cost_m": round(cost, 2),
            "driver_door": car["driver_door"], "front_stop": car["front_stop"],
            "strategy": "intercept_front_then_driver_door" if moving else "approach_driver_door",
            "selection_cost": cost + (12 if moving else 0) + (4 if car["occupied"] else 0)})
    return sorted(candidates, key=lambda c: c["selection_cost"])[:8]


def local_point(car, x, y):
    return {"x": car["position"]["x"]+car["right_xy"]["x"]*x+car["forward_xy"]["x"]*y,
            "y": car["position"]["y"]+car["right_xy"]["y"]*x+car["forward_xy"]["y"]*y,
            "z": car["position"]["z"]}


def crosses_car(start, end, car, margin=0.35):
    """Segment/rotated-footprint test; walking to a door must not cross the hood."""
    def transform(p):
        delta = {a: p[a]-car["position"][a] for a in ("x", "y")}
        return [sum(delta[a]*car[b][a] for a in ("x", "y")) for b in ("right_xy", "forward_xy")]
    a, b = transform(start), transform(end)
    low, high = 0.001, 0.999
    for axis, lower, upper in ((0, -car["half_width"]-margin, car["half_width"]+margin),
                               (1, car["rear_extent"]-margin, car["front_extent"]+margin)):
        delta = b[axis]-a[axis]
        if abs(delta) < 1e-8:
            if not lower < a[axis] < upper:
                return False
        else:
            p, q = (lower-a[axis])/delta, (upper-a[axis])/delta
            low, high = max(low, min(p,q)), min(high, max(p,q))
            if low >= high:
                return False
    return low < high


def around_car(start, goal, car):
    if not crosses_car(start, goal, car, 0.2):
        return goal
    corners = [local_point(car, side*(car["half_width"]+0.9), end)
               for side in (-1, 1) for end in (car["front_extent"]+1.0, car["rear_extent"]-1.0)]
    points = [start, *corners, goal]
    queue, costs, parents = [(0, 0)], {0: 0}, {}
    while queue:
        cost, i = heapq.heappop(queue)
        if cost != costs[i]:
            continue
        if i == len(points)-1:
            while parents.get(i) != 0:
                i = parents[i]
            return points[i]
        for j in range(1, len(points)):
            if i == j or crosses_car(points[i], points[j], car, 0.2):
                continue
            candidate = cost + distance(points[i], points[j])
            if candidate < costs.get(j, math.inf):
                costs[j], parents[j] = candidate, i
                heapq.heappush(queue, (candidate, j))
    return None


@dataclass(frozen=True)
class ControlIntent:
    action: str = "idle"
    goal: dict | None = None
    reason: str = "waiting"


class CarAcquisition:
    """Persistent target and explicit intercept/door/entry/hold phases."""
    def __init__(self):
        self.target = None
        self.phase = "select_target"
        self.excluded = {}
        self.reason = "waiting_for_jev_target"
        self.last_entry = -100.0
        self.entry_attempts = 0
        self.stopped_since = None
        self.checkpoint = None
        self.recovery_until = 0
        self.recoveries = 0
        self.route = []
        self.next_route = 0
        self.last_goal = None
        self.scout_goal = None
        self.door_blocked_since = self.intercept_wait_since = None
        self.last_wrong_vehicle_exit = -100.0

    def progress(self, state, elapsed):
        self.excluded = {ref: end for ref, end in self.excluded.items() if end > elapsed}
        return {"phase": self.phase, "target_vehicle_reference": self.target, "reason": self.reason,
                "entry_attempts": self.entry_attempts, "route_waypoints": self.route[:8],
                "candidates": candidate_cars(state, self.excluded) if self.target is None else []}

    def accept(self, plan, state, elapsed):
        if self.target is not None or not plan:
            return False
        ref = plan.get("target_vehicle_reference")
        choices = {c["reference"]: c for c in candidate_cars(state, self.excluded)}
        if ref not in choices:
            return False
        self.target = ref
        self.phase = "intercept_front" if choices[ref]["speed_mps"] > 0.7 else "approach_driver_door"
        self.reason = "jev_selected_vehicle"
        self.entry_attempts = self.recoveries = 0
        self.checkpoint = None
        self.next_route = 0
        self.scout_goal = None
        self.door_blocked_since = self.intercept_wait_since = None
        return True

    def reject(self, elapsed, reason):
        if self.target is not None:
            self.excluded[self.target] = elapsed+12
        self.target, self.phase, self.reason = None, "select_target", reason
        self.route, self.checkpoint = [], None

    def _steer(self, state, waypoint, car, elapsed, close=False):
        player = state["player"]["position"]
        if car and crosses_car(player, waypoint, car, 0.2):
            waypoint = around_car(player, waypoint, car)
            if waypoint is None:
                return ControlIntent(reason="no_clear_route_around_target")
        d = distance(player, waypoint)
        if d <= 0.45:
            return ControlIntent(reason="waypoint_reached")
        desired = math.atan2(-(waypoint["x"]-player["x"]), waypoint["y"]-player["y"])
        choices = []
        vehicles = [v for v in vehicle_map(state).values() if abs(v["position"]["z"]-player["z"]) < 3]
        for ray in state["navigation"]["rays"]:
            angle = ray["heading_radians"]
            error = abs(math.atan2(math.sin(angle-desired), math.cos(angle-desired)))
            step = min(1.5, d)
            if ray["clearance_m"] < min(step+0.3, 1.6):
                continue
            goal = {"x": player["x"]-math.sin(angle)*step,
                    "y": player["y"]+math.cos(angle)*step, "z": player["z"]}
            if any(abs(other["position"]["z"]-player["z"]) < 3 and crosses_car(player, goal, other, 0.25)
                   for other in vehicles):
                continue
            score = error + 0.2/max(0.2, ray["clearance_m"])
            if elapsed < self.recovery_until:
                # A bounded, repeatable side-step; no random key selection.
                side = 1 if self.recoveries % 2 else -1
                recovery = desired + side*math.pi/2
                score = abs(math.atan2(math.sin(angle-recovery), math.cos(angle-recovery)))
            choices.append((score, goal))
        if not choices:
            return ControlIntent(reason="blocked_by_geometry_or_vehicle")
        _, goal = min(choices, key=lambda item: item[0])
        # Aim exactly at a close, clear goal instead of orbiting it on a 16-ray grid.
        nearest_ray = min(state["navigation"]["rays"], key=lambda r: abs(math.atan2(
            math.sin(r["heading_radians"]-desired), math.cos(r["heading_radians"]-desired))))
        if (d < 2.0 and elapsed >= self.recovery_until and nearest_ray["clearance_m"] >= d+0.15 and
            not any(crosses_car(player, waypoint, other, 0.2) for other in vehicles)):
            goal = waypoint
        self.last_goal = goal
        return ControlIntent("world_walk" if close or d < 3 else "world_run",
                             {**goal, "stop_radius_m": 0.3}, "following_road_and_clearance_route")

    def tick(self, state, elapsed):
        player, nav = state["player"], state["navigation"]
        if nav["entering_vehicle"]:
            self.phase, self.reason = "wait_for_entry", "entry_animation_in_progress"
            return ControlIntent(reason=self.reason)
        if player["in_vehicle"]:
            vehicle = state.get("vehicle") or {}
            if vehicle.get("vehicle_class") == 0 and vehicle.get("is_driver"):
                self.phase = "hold_driver_seat"
                self.reason = "never_press_exit_after_entry"
                return ControlIntent(reason=self.reason)
            self.phase = "leave_wrong_vehicle"
            if elapsed-self.last_wrong_vehicle_exit > 5:
                self.last_wrong_vehicle_exit = elapsed
                return ControlIntent("enter_exit", reason="exit_bicycle_or_passenger_seat_once")
            return ControlIntent(reason="waiting_to_leave_wrong_vehicle")
        if self.phase == "leave_wrong_vehicle":
            self.reject(elapsed, "wrong_vehicle_entered_reselect_automobile")
            return ControlIntent(reason=self.reason)
        if self.target is None:
            self.phase = "select_target"
            # If no reachable car is available, observe traffic from a nearby
            # clear road node instead of wandering around in arbitrary directions.
            if not candidate_cars(state, self.excluded):
                roads = [n for n in nav["nodes"] if n["road"] and n["visible"] and
                         2 < distance(player["position"], n["position"]) < 90]
                if self.scout_goal is None and roads:
                    self.scout_goal = min(roads, key=lambda n: distance(player["position"], n["position"]))["position"]
                if self.scout_goal and distance(player["position"], self.scout_goal) > 1:
                    return self._steer(state, self.scout_goal, None, elapsed, close=True)
            return ControlIntent(reason="waiting_for_jev_target")
        car = vehicle_map(state).get(self.target)
        if not car or not car["is_automobile"] or not car["openable"] or car["health"] <= 300:
            self.reject(elapsed, "target_lost_or_unusable")
            return ControlIntent(reason=self.reason)
        if car["speed_mps"] > 5:
            self.reject(elapsed, "target_traffic_too_fast")
            return ControlIntent(reason=self.reason)
        if self.phase == "wait_for_entry":
            if elapsed-self.last_entry < 8:
                return ControlIntent(reason="waiting_for_driver_entry_without_repeated_F")
            if self.entry_attempts >= 2:
                self.reject(elapsed, "entry_attempts_exhausted")
                return ControlIntent(reason=self.reason)
            self.phase = "approach_driver_door"
        if self.phase == "intercept_front":
            if car["speed_mps"] <= 0.7:
                self.stopped_since = self.stopped_since if self.stopped_since is not None else elapsed
                if elapsed-self.stopped_since >= 0.4:
                    self.phase, self.next_route = "approach_driver_door", 0
            else:
                self.stopped_since = None
        elif car["speed_mps"] > 1.5:
            self.phase, self.next_route = "intercept_front", 0
        front = self.phase == "intercept_front"
        goal = car["front_stop"] if front else door_goal(car)
        goal_distance = distance(player["position"], goal)
        if front and goal_distance < 1.2:
            self.intercept_wait_since = self.intercept_wait_since if self.intercept_wait_since is not None else elapsed
            if elapsed-self.intercept_wait_since > 4:
                self.reject(elapsed, "traffic_would_not_stop")
                return ControlIntent(reason=self.reason)
            self.reason = "standing_in_front_waiting_for_traffic_to_stop"
            return ControlIntent(reason=self.reason)
        self.intercept_wait_since = None
        if not front and distance(player["position"], car["driver_door"]) <= 1.25:
            other_close = any(v["reference"] != self.target and
                distance(player["position"], v["position"]) < 1.5
                for v in state["world"]["nearby_vehicles"])
            if car["speed_mps"] <= 0.7 and car["door_clear"] and not car["door_busy"] and not other_close:
                self.phase, self.last_entry = "wait_for_entry", elapsed
                self.entry_attempts += 1
                self.door_blocked_since = None
                self.reason = "at_selected_driver_door_press_F_once"
                return ControlIntent("enter_exit", reason=self.reason)
            self.door_blocked_since = self.door_blocked_since if self.door_blocked_since is not None else elapsed
            if elapsed-self.door_blocked_since > 4:
                self.reject(elapsed, "driver_door_ambiguous_or_blocked")
            return ControlIntent(reason="waiting_for_clear_stopped_driver_door")
        self.door_blocked_since = None
        if self.checkpoint is None:
            self.checkpoint = (elapsed, dict(player["position"]), goal_distance)
        elif elapsed-self.checkpoint[0] > 4:
            _, position, previous_distance = self.checkpoint
            if distance(position, player["position"]) < 0.7:
                self.recoveries += 1
                self.recovery_until, self.next_route = elapsed+1.2, 0
                if self.recoveries >= 3:
                    self.reject(elapsed, "route_stalled_choose_another_car")
                    return ControlIntent(reason=self.reason)
            elif previous_distance-goal_distance < 0.3:
                # A legitimate trip around the hood or a wall can temporarily
                # increase straight-line distance. Replan without penalizing it.
                self.next_route = 0
            self.checkpoint = (elapsed, dict(player["position"]), goal_distance)
        if elapsed >= self.next_route:
            self.route, _ = road_route(state, car, front)
            self.next_route = elapsed+0.6
        while self.route and distance(player["position"], self.route[0]) < 1.5:
            self.route.pop(0)
        waypoint = self.route[0] if self.route else goal
        self.reason = "intercept_traffic_front" if front else "go_around_to_driver_door"
        return self._steer(state, waypoint, car, elapsed, close=not front and goal_distance < 5)
