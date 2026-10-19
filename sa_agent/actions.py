"""Bounded pad actions shared with src/agent_protocol.h; no arbitrary memory writes."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    code: int
    description: str


ACTIONS = {
    "idle": Action(0, "Release controls and briefly wait."),
    "forward": Action(1, "Walk forward relative to the camera."),
    "backward": Action(2, "Walk backward relative to the camera."),
    "left": Action(3, "Walk left relative to the camera."),
    "right": Action(4, "Walk right relative to the camera."),
    "sprint": Action(5, "Move forward while sprinting."),
    "jump": Action(6, "Move forward and press jump/climb."),
    "enter_exit": Action(7, "Press the enter/exit vehicle button; approach a driver door first."),
    "accelerate": Action(8, "Accelerate the vehicle straight ahead."),
    "brake": Action(9, "Apply the vehicle brake; holding it at rest can reverse."),
    "steer_left": Action(10, "Steer left without adding throttle."),
    "steer_right": Action(11, "Steer right without adding throttle."),
    "reverse": Action(12, "Hold brake/reverse to move the vehicle backward."),
    "handbrake": Action(13, "Apply the vehicle handbrake."),
    "forward_left": Action(14, "Walk diagonally forward-left relative to the camera."),
    "forward_right": Action(15, "Walk diagonally forward-right relative to the camera."),
    "accelerate_left": Action(16, "Accelerate and steer left."),
    "accelerate_right": Action(17, "Accelerate and steer right."),
    "world_walk": Action(18, "Walk toward a bounded world-coordinate waypoint."),
    "world_run": Action(19, "Run toward a bounded world-coordinate waypoint."),
    "world_sprint": Action(20, "Sprint toward a bounded world-coordinate waypoint."),
    "attack": Action(21, "Hold the normal fire/melee button using the equipped weapon."),
    "aim": Action(22, "Hold normal game targeting; game aim assistance may apply."),
    "aim_attack": Action(23, "Hold normal targeting and fire/melee together."),
    "aim_left": Action(24, "Hold targeting and move the right stick left at half strength."),
    "aim_right": Action(25, "Hold targeting and move the right stick right at half strength."),
    "aim_up": Action(26, "Hold targeting and move the right stick up at half strength."),
    "aim_down": Action(27, "Hold targeting and move the right stick down at half strength."),
    "weapon_next": Action(28, "Cycle to the next available weapon once."),
    "weapon_previous": Action(29, "Cycle to the previous available weapon once."),
}

ON_FOOT = {"idle", "forward", "backward", "left", "right", "forward_left", "forward_right",
           "sprint", "jump", "enter_exit", "world_walk", "world_run", "world_sprint",
           "attack", "aim", "aim_attack", "aim_left", "aim_right", "aim_up", "aim_down",
           "weapon_next", "weapon_previous"}
IN_VEHICLE = {"idle", "enter_exit", "accelerate", "brake", "reverse", "steer_left",
              "steer_right", "handbrake", "accelerate_left", "accelerate_right"}


def available_actions(task, state):
    mode = IN_VEHICLE if state["player"]["in_vehicle"] else ON_FOOT
    names = [name for name in task["allowed_actions"] if name in mode]
    if not names or "idle" not in names:
        raise ValueError("The task must allow idle and at least one action for the current mode")
    return {name: ACTIONS[name].description for name in names}
