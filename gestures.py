"""검지 중심의 그리기 판정, 주먹/핀치, 호버 타이머."""
import numpy as np
from collections import deque

import config


def fingers_extended(lm):
    # 정규화 x/y의 종횡비를 복원해 손 회전에 따른 거리 왜곡 방지.
    points = np.asarray(lm, dtype=float)[:, :2] * (
        config.CAMERA_WIDTH / config.CAMERA_HEIGHT, 1.0
    )
    wrist = points[0]
    return tuple(
        np.linalg.norm(points[tip] - wrist)
        > config.FINGER_EXTEND_RATIO * np.linalg.norm(points[joint] - wrist)
        for tip, joint in ((4, 3), (8, 6), (12, 10), (16, 14), (20, 18))
    )


def pinch_ratio(lm):
    points = np.asarray(lm, dtype=float)[:, :2] * (
        config.CAMERA_WIDTH / config.CAMERA_HEIGHT, 1.0
    )
    size = np.linalg.norm(points[9] - points[0])
    if size < 1e-8:
        return float("inf")
    index_reach = np.linalg.norm(points[8] - points[0])
    thumb_reach = np.linalg.norm(points[4] - points[0])
    if (index_reach <= config.PINCH_INDEX_REACH_RATIO * np.linalg.norm(points[6] - points[0])
            or thumb_reach <= config.PINCH_THUMB_REACH_RATIO * np.linalg.norm(points[2] - points[0])):
        return float("inf")
    return float(np.linalg.norm(points[4] - points[8]) / size)


def index_ready(lm, drawing=False):
    # z도 사용해 손가락이 카메라 쪽을 향할 때의 2D 거리 축소를 보완.
    points = np.asarray(lm, dtype=float) * (
        config.CAMERA_WIDTH / config.CAMERA_HEIGHT, 1.0,
        config.CAMERA_WIDTH / config.CAMERA_HEIGHT,
    )
    pip_distance = np.linalg.norm(points[6] - points[0])
    if pip_distance < 1e-8:
        return False
    ratio = np.linalg.norm(points[8] - points[0]) / pip_distance
    threshold = config.DRAW_INDEX_HOLD_RATIO if drawing else config.DRAW_INDEX_ENTER_RATIO
    if ratio > threshold:
        return True
    a, b = points[5] - points[6], points[8] - points[6]
    length = np.linalg.norm(a) * np.linalg.norm(b)
    if length < 1e-8:
        return False
    angle = np.degrees(np.arccos(np.clip(np.dot(a, b) / length, -1, 1)))
    return ratio > config.DRAW_INDEX_HOLD_RATIO and angle >= config.DRAW_INDEX_MIN_ANGLE


def classify(lm, pinching=False, drawing=False):
    thumb, index, middle, ring, pinky = fingers_extended(lm)
    threshold = config.PINCH_RELEASE_RATIO if pinching else config.PINCH_ENTER_RATIO
    if pinch_ratio(lm) < threshold:
        return "PINCH"
    # 엄지 위치와 다른 손가락의 약간의 펼침은 그리기를 막지 않는다.
    # 손바닥을 완전히 펼친 자세는 펜 업으로 남겨 양손 생성과 구분.
    if index_ready(lm, drawing=drawing) and not all((middle, ring, pinky)):
        return "DRAW"
    if not any((thumb, index, middle, ring, pinky)):
        return "FIST"
    return "IDLE"


class GestureDebouncer:
    def __init__(self):
        self.reset()

    def reset(self):
        self.current = "IDLE"
        self.candidate = None
        self.count = 0

    def update(self, gesture):
        if gesture == self.candidate:
            self.count += 1
        else:
            self.candidate, self.count = gesture, 1
        required = (config.DRAW_START_FRAMES if gesture == "DRAW"
                    else config.GESTURE_DEBOUNCE_FRAMES)
        if self.count >= required:
            self.current = gesture
        return self.current


class DwellSelector:
    def __init__(self):
        self.reset()

    def reset(self):
        self.target = None
        self.started = None
        self.fired = False
        self.progress = 0.0

    def update(self, target, now, duration):
        if target is None:
            self.reset()
            return None
        if target != self.target:
            self.target, self.started = target, now
            self.fired = False
        self.progress = min(max((now - self.started) / duration, 0.0), 1.0)
        if self.progress >= 1.0 and not self.fired:
            self.fired = True
            return target
        return None


class ThrowDetector:
    def __init__(self):
        self.samples = deque()

    def reset(self):
        self.samples.clear()

    def update(self, point, now, width, height):
        while self.samples and now - self.samples[0][0] > config.THROW_WINDOW_SECONDS:
            self.samples.popleft()
        self.samples.append((now, float(point[0]) / width, float(point[1]) / height))

    def ready(self, now, require_outside=False):
        if len(self.samples) < 2:
            return False
        last, x, y = self.samples[-1]
        if now - last > config.THROW_RELEASE_SECONDS:
            return False
        first, old_x, old_y = self.samples[0]
        dt = last - first
        if dt < 0.05:
            return False
        margin = 0.0 if require_outside else config.THROW_EDGE_MARGIN
        candidates = ((x <= margin, old_x-x), (x >= 1-margin, x-old_x),
                      (y <= margin, old_y-y), (y >= 1-margin, y-old_y))
        return any(edge and distance >= config.THROW_MIN_DISTANCE and
                   distance / dt >= config.THROW_MIN_SPEED for edge, distance in candidates)


class SpreadDetector:
    def __init__(self):
        self.history = deque()
        self.open_frames = 0
        self.confirm_frames = 0
        self.latched = False
        self.last_trigger = float("-inf")
        self.pair = None
        self.last_open = None
        self.progress = 0.0

    @staticmethod
    def palm_open(lm):
        points = np.asarray(lm, dtype=float) * (config.CAMERA_WIDTH/config.CAMERA_HEIGHT,
                                               1, config.CAMERA_WIDTH/config.CAMERA_HEIGHT)
        extended = sum(np.linalg.norm(points[tip]-points[0]) >
                       config.SPREAD_FINGER_RATIO*np.linalg.norm(points[joint]-points[0])
                       for tip,joint in ((8,6),(12,10),(16,14),(20,18)))
        return extended >= config.SPREAD_MIN_EXTENDED

    def update(self, hands, now):
        opened = len(hands) == 2 and all(self.palm_open(h["lm"]) for h in hands)
        if not opened:
            if self.last_open is not None and now-self.last_open <= config.SPREAD_MISS_SECONDS:
                return False
            self.history.clear()
            self.open_frames = self.confirm_frames = 0
            self.latched = False
            self.pair = None
            self.progress = 0.0
            return False
        # 좌우 라벨이 흔들려도 두 손의 대칭적인 손목 거리를 유지한다.
        if self.last_open is not None and now-self.last_open > config.SPREAD_MISS_SECONDS:
            self.history.clear()
            self.open_frames = self.confirm_frames = 0
        self.last_open = now
        self.open_frames += 1
        if self.latched or now - self.last_trigger < config.SPREAD_COOLDOWN_SECONDS:
            self.history.clear()
            return False
        delta = np.asarray(hands[0]["lm"])[0, :2] - np.asarray(hands[1]["lm"])[0, :2]
        distance = float(np.linalg.norm(delta * (1.0, config.CAMERA_HEIGHT / config.CAMERA_WIDTH)))
        while self.history and now - self.history[0][0] > config.SPREAD_WINDOW_SECONDS:
            self.history.popleft()
        self.history.append((now, distance))
        baseline_time, baseline = min(self.history, key=lambda sample: sample[1])
        increase = distance - baseline
        self.progress = min(max(increase/config.SPREAD_MIN_INCREASE,0.0),1.0)
        speed = increase / max(now-baseline_time,1e-6)
        if (self.open_frames >= config.SPREAD_OPEN_FRAMES and increase >= config.SPREAD_MIN_INCREASE
                and speed >= config.SPREAD_MIN_SPEED):
            self.confirm_frames += 1
        else:
            self.confirm_frames = 0
        if self.confirm_frames >= config.SPREAD_CONFIRM_FRAMES:
            self.latched = True
            self.last_trigger = now
            self.history.clear()
            return True
        return False
