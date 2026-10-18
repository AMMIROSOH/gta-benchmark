import copy
import math
import unittest

from sa_agent.navigation import (CarAcquisition, around_car, candidate_cars, crosses_car,
                                 door_goal, distance, road_route, vehicle_map)


def point(x, y, z=1):
    return {"x": x, "y": y, "z": z}


def fixture():
    car = {"reference": 257, "model_id": 400, "is_automobile": True, "vehicle_class": 0,
           "position": point(0, 0), "health": 1000, "speed_mps": 0, "occupied": True}
    geometry = {"reference": 257, "openable": True, "door_clear": True, "front_clear": True,
        "door_busy": False, "driver_door_valid": True, "driver_door": point(-1.5, 0.5),
        "front_stop": point(0, 5.5), "velocity_xy": {"x": 0, "y": 0},
        "right_xy": {"x": 1, "y": 0}, "forward_xy": {"x": 0, "y": 1},
        "half_width": 1, "front_extent": 2.5, "rear_extent": -2.5,
        "door_anchors": [], "front_anchors": []}
    return {"player": {"position": point(-6, 0), "in_vehicle": False, "health": 100},
        "vehicle": None, "world": {"nearby_vehicles": [car]},
        "navigation": {"world_goals_ready": True, "sample_age_ms": 0, "entering_vehicle": False,
            "camera_orientation": 0, "nodes": [], "vehicles": [geometry],
            "rays": [{"heading_radians": i*math.tau/16, "clearance_m": 8,
                      "ground_delta_m": 0} for i in range(16)]}}


class CarNavigationTests(unittest.TestCase):
    def test_bicycle_and_locked_car_are_not_targets(self):
        state = fixture()
        bike = copy.deepcopy(state["world"]["nearby_vehicles"][0])
        bike.update(reference=513, is_automobile=False, model_id=481, position=point(-6, .3))
        geometry = copy.deepcopy(state["navigation"]["vehicles"][0])
        geometry.update(reference=513, driver_door_valid=False)
        state["world"]["nearby_vehicles"].append(bike)
        state["navigation"]["vehicles"].append(geometry)
        self.assertEqual([257], [c["reference"] for c in candidate_cars(state)])
        state["navigation"]["vehicles"][0]["openable"] = False
        self.assertEqual([], candidate_cars(state))

    def test_recycled_pool_reference_is_not_the_locked_target(self):
        state, controller = fixture(), CarAcquisition()
        self.assertTrue(controller.accept({"target_vehicle_reference": 257}, state, 0))
        state["world"]["nearby_vehicles"][0]["reference"] = 258
        state["navigation"]["vehicles"][0]["reference"] = 258
        self.assertEqual("idle", controller.tick(state, 1).action)
        self.assertIsNone(controller.target)
        self.assertEqual("target_lost_or_unusable", controller.reason)

    def test_target_stays_locked_when_another_car_appears(self):
        state, controller = fixture(), CarAcquisition()
        controller.accept({"target_vehicle_reference": 257}, state, 0)
        self.assertFalse(controller.accept({"target_vehicle_reference": 999}, state, 1))
        self.assertEqual(257, controller.target)

    def test_route_uses_linked_road_around_a_wall(self):
        state = fixture()
        state["player"]["position"] = point(-20, 0)
        geometry = state["navigation"]["vehicles"][0]
        geometry.update(door_clear=False, door_anchors=[3])
        state["navigation"]["nodes"] = [
            {"reference": 1, "road": True, "visible": True, "position": point(-18, 0), "links": [2]},
            {"reference": 2, "road": True, "visible": False, "position": point(-18, 12), "links": [1,3]},
            {"reference": 3, "road": True, "visible": False, "position": point(-4, 12), "links": [2]}]
        route, cost = road_route(state, vehicle_map(state)[257])
        self.assertEqual([point(-18,0), point(-18,12), point(-4,12)], route[:-1])
        self.assertTrue(math.isfinite(cost))

    def test_alley_can_connect_to_a_visible_sidewalk_over_18_metres_away(self):
        state = fixture()
        state["player"]["position"] = point(-30,0)
        geometry = state["navigation"]["vehicles"][0]
        geometry.update(door_clear=False, door_anchors=[2])
        state["navigation"]["nodes"] = [
            {"reference": 1, "road": False, "visible": True, "position": point(-6,4), "links": [2]},
            {"reference": 2, "road": True, "visible": False, "position": point(-4,4), "links": [1]}]
        route, cost = road_route(state, vehicle_map(state)[257])
        self.assertTrue(route)
        self.assertTrue(math.isfinite(cost))
        self.assertEqual([257], [c["reference"] for c in candidate_cars(state)])

    def test_scout_can_leave_an_alley_when_the_road_is_more_than_15_metres_away(self):
        state, controller = fixture(), CarAcquisition()
        state["world"]["nearby_vehicles"] = []
        state["navigation"]["nodes"] = [{"reference": 1, "road": True, "visible": True,
            "position": point(-6,30), "links": []}]
        self.assertIsNotNone(controller.tick(state, 0).goal)

    def test_rotated_car_detour_does_not_cross_its_body(self):
        state = fixture()
        car = vehicle_map(state)[257]
        for angle in (0, math.pi/2, -1.1):
            car["right_xy"] = {"x": math.cos(angle), "y": math.sin(angle)}
            car["forward_xy"] = {"x": -math.sin(angle), "y": math.cos(angle)}
            def rotate(p):
                return point(p["x"]*math.cos(angle)-p["y"]*math.sin(angle),
                             p["x"]*math.sin(angle)+p["y"]*math.cos(angle))
            start, target = rotate(point(4,0)), rotate(point(-1.8,.5))
            for _ in range(5):
                waypoint = around_car(start, target, car)
                self.assertIsNotNone(waypoint)
                self.assertFalse(crosses_car(start, waypoint, car, .2))
                if distance(waypoint, target) < .01:
                    break
                start = waypoint
            else:
                self.fail("Vehicle detour did not reach the driver side")

    def test_moving_traffic_is_intercepted_then_door_is_approached(self):
        state, controller = fixture(), CarAcquisition()
        state["player"]["position"] = point(0, 7)
        state["world"]["nearby_vehicles"][0]["speed_mps"] = 1.5
        controller.accept({"target_vehicle_reference": 257}, state, 0)
        self.assertEqual("intercept_front", controller.phase)
        self.assertTrue(controller.tick(state, .1).action.startswith("world_"))
        state["world"]["nearby_vehicles"][0]["speed_mps"] = 0
        controller.tick(state, .2)
        controller.tick(state, .7)
        self.assertEqual("approach_driver_door", controller.phase)

    def test_fast_traffic_from_behind_is_not_chased(self):
        state = fixture()
        state["world"]["nearby_vehicles"][0]["speed_mps"] = 3.5
        self.assertEqual([], candidate_cars(state))

    def test_entry_is_one_pulse_and_animation_is_not_cancelled(self):
        state, controller = fixture(), CarAcquisition()
        state["player"]["position"] = point(-1.8, .5)
        controller.accept({"target_vehicle_reference": 257}, state, 0)
        self.assertEqual("enter_exit", controller.tick(state, 1).action)
        self.assertEqual("idle", controller.tick(state, 1.1).action)
        state["navigation"]["entering_vehicle"] = True
        self.assertEqual("idle", controller.tick(state, 12).action)
        state["navigation"]["entering_vehicle"] = False
        state["player"]["in_vehicle"] = True
        state["vehicle"] = {"vehicle_class": 0, "is_driver": True}
        self.assertEqual("idle", controller.tick(state, 14).action)
        self.assertEqual("hold_driver_seat", controller.phase)

    def test_accidental_bicycle_entry_is_recovered_without_toggle_spam(self):
        state, controller = fixture(), CarAcquisition()
        state["player"]["in_vehicle"] = True
        state["vehicle"] = {"vehicle_class": 10, "is_driver": True}
        state["navigation"]["entering_vehicle"] = True
        self.assertEqual("idle", controller.tick(state, 0).action)
        state["navigation"]["entering_vehicle"] = False
        self.assertEqual("enter_exit", controller.tick(state, 1).action)
        self.assertEqual("idle", controller.tick(state, 1.1).action)
        state["player"]["in_vehicle"] = False
        controller.tick(state, 2)
        self.assertEqual("select_target", controller.phase)

    def test_other_bicycle_near_door_blocks_blind_enter_press(self):
        state, controller = fixture(), CarAcquisition()
        state["player"]["position"] = point(-1.8, .5)
        controller.accept({"target_vehicle_reference": 257}, state, 0)
        state["world"]["nearby_vehicles"].append({"reference": 513, "position": point(-1.8, 1),
                                                "is_automobile": False})
        self.assertEqual("idle", controller.tick(state, 1).action)
        controller.tick(state, 5.2)
        self.assertIsNone(controller.target)

    def test_waiting_in_front_of_non_stopping_traffic_is_bounded(self):
        state, controller = fixture(), CarAcquisition()
        state["player"]["position"] = point(0, 5.5)
        state["world"]["nearby_vehicles"][0]["speed_mps"] = 1
        controller.accept({"target_vehicle_reference": 257}, state, 0)
        self.assertEqual("idle", controller.tick(state, 1).action)
        controller.tick(state, 5.2)
        self.assertIsNone(controller.target)
        self.assertEqual("traffic_would_not_stop", controller.reason)

    def test_closed_loop_walk_reaches_door_before_pressing_enter(self):
        for start in (point(-6,0), point(6,0), point(0,8), point(0,-8)):
            with self.subTest(start=start):
                self.walk_to_door(start)

    def walk_to_door(self, start):
        state, controller = fixture(), CarAcquisition()
        state["player"]["position"] = start
        controller.accept({"target_vehicle_reference": 257}, state, 0)
        car = vehicle_map(state)[257]
        for step in range(300):
            intent = controller.tick(state, step*.1)
            if intent.action == "enter_exit":
                self.assertLessEqual(distance(state["player"]["position"], car["driver_door"]), 1.25)
                return
            if intent.goal:
                p, goal = state["player"]["position"], intent.goal
                d = distance(p, goal)
                amount = min(max(0, d-goal["stop_radius_m"]), .16 if intent.action == "world_walk" else .3)
                if d:
                    state["player"]["position"] = {**p, "x": p["x"]+(goal["x"]-p["x"])*amount/d,
                                                   "y": p["y"]+(goal["y"]-p["y"])*amount/d}
        self.fail("Closed-loop movement failed to reach the selected driver door")


if __name__ == "__main__":
    unittest.main()
