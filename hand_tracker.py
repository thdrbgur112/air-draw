import time

import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

import config


class HandTracker:
    def __init__(self):
        opts = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=config.MODEL_PATH),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=config.NUM_HANDS,
            min_hand_detection_confidence=config.MIN_DETECTION_CONF,
            min_hand_presence_confidence=config.MIN_PRESENCE_CONF,
            min_tracking_confidence=config.MIN_TRACKING_CONF,
        )
        self.landmarker = vision.HandLandmarker.create_from_options(opts)
        self.t0 = time.monotonic()
        self.last_ts = -1

    def detect(self, rgb):
        """rgb: 거울 모드 HxWx3 uint8. 반환: [{'lm': (21,3) 정규화 좌표, 'side': 'Left'|'Right'}]"""
        ts = max(int((time.monotonic() - self.t0) * 1000), self.last_ts + 1)
        self.last_ts = ts
        r = self.landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)
        return [
            {"lm": np.array([[p.x, p.y, p.z] for p in hand], dtype=np.float32), "side": h[0].category_name}
            for hand, h in zip(r.hand_landmarks, r.handedness)
        ]

    def close(self):
        self.landmarker.close()


def to_screen(x, y, w, h, camera_aligned=False, clamp=True):
    """카메라 배경은 영상과 일치, 투명 모드는 중앙 MAP_REGION 확대 매핑."""
    if camera_aligned:
        # QPainter.drawImage(self.rect(), image)와 같은 전체 프레임 매핑.
        if not clamp:
            return float(x) * w, float(y) * h
        return min(max(float(x) * w, 0.0), w - 1), min(max(float(y) * h, 0.0), h - 1)
    rw, rh = config.MAP_REGION_W, config.MAP_REGION_H
    u = (x - (1 - rw) / 2) / rw
    v = (y - (1 - rh) / 2) / rh
    if not clamp:
        return float(u) * (w - 1), float(v) * (h - 1)
    return min(max(u, 0.0), 1.0) * (w - 1), min(max(v, 0.0), 1.0) * (h - 1)


class EMA:
    def __init__(self, alpha):
        self.alpha = alpha
        self.value = None

    def __call__(self, p):
        p = np.asarray(p, dtype=np.float64)
        self.value = p if self.value is None else self.alpha * p + (1 - self.alpha) * self.value
        return self.value

    def reset(self):
        self.value = None


if __name__ == "__main__":
    assert to_screen(0.5, 0.5, 1001, 1001) == (500.0, 500.0)
    assert to_screen(0.0, 1.0, 1001, 1001) == (0.0, 1000.0)  # 영역 밖은 클램프
    assert to_screen(0.15, 0.85, 1001, 1001) == (0.0, 1000.0)  # 영역 경계 = 화면 경계
    e = EMA(0.5)
    e((0, 0))
    assert tuple(e((10, 10))) == (5, 5)
    print("ok")
