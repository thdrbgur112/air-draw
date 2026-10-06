import time

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

import config
from hand_tracker import HandTracker


class CameraWorker(QThread):
    frame_ready = Signal(object, object, float)  # hands, 프리뷰 QImage, fps
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        # 메인 스레드에서 열어야 macOS 카메라 권한 요청 창이 뜬다
        cap = cv2.VideoCapture(config.CAMERA_INDEX, cv2.CAP_AVFOUNDATION)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, config.CAMERA_FPS)
        self.cap = cap
        if cap.isOpened():
            print(f"camera {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")

    def run(self):
        cap = self.cap
        if not cap.isOpened():
            self.failed.emit("카메라를 열 수 없습니다. 시스템 설정 > 개인정보 보호 및 보안 > 카메라에서 이 앱을 실행한 터미널(또는 IDE)을 허용한 뒤 다시 실행하세요.")
            return

        tracker = HandTracker()
        fps, last = 0.0, time.monotonic()
        misses = 0
        while not self.isInterruptionRequested():
            ok, frame = cap.read()
            if not ok:
                misses += 1
                if misses > 60:
                    self.failed.emit("카메라 프레임을 읽지 못했습니다 (권한 또는 다른 앱 점유 확인).")
                    break
                continue
            misses = 0
            rgb = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
            hands = tracker.detect(rgb)

            # 같은 원본 프레임을 전체화면 배경과 작은 프리뷰에서 각각 스케일링.
            img = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format_RGB888).copy()

            now = time.monotonic()
            fps = 0.9 * fps + 0.1 / max(now - last, 1e-6) if fps else 1 / max(now - last, 1e-6)
            last = now
            self.frame_ready.emit(hands, img, fps)

        tracker.close()
        cap.release()
