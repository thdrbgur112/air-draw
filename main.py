import signal
import sys
import time
import numpy as np

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
from PySide6.QtCore import QTimer

import config
from camera_worker import CameraWorker
from hand_tracker import EMA, to_screen
from gestures import DwellSelector, GestureDebouncer, SpreadDetector, ThrowDetector, classify, pinch_ratio
from overlay import Overlay, hide_from_dock
from preview import Preview
from codex_bridge import CodexBridge
from result_panel import ResultPanel
from controls import Controls

INDEX_TIP = 8


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)  # 터미널 Ctrl+C로 종료
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    hide_from_dock()

    overlay = Overlay()
    preview = Preview()
    worker = CameraWorker()
    cursor_ema = EMA(config.CURSOR_EMA_ALPHA)
    pinch_ema = EMA(config.CURSOR_EMA_ALPHA)
    gestures = GestureDebouncer()
    dwell = DwellSelector()
    spread = SpreadDetector()
    throw = ThrowDetector()
    transition_started = None
    state = "IDLE"
    active_side = None
    bridge = None
    panel = None
    sketch_path = None
    generation_started = None
    error_started = None
    fist_started = None
    last_erase_pos = None
    last_draw_seen = None
    last_hand_seen = None
    ui_release_rect = None

    def transition(next_state):
        nonlocal state
        if state == next_state:
            return
        print(f"state: {state} -> {next_state}", flush=True)
        if state == "DRAWING":
            overlay.canvas.finish()
        if state == "GRABBING":
            overlay.canvas.release()
            pinch_ema.reset()
            throw.reset()
        state = next_state
        overlay.mode = {"DRAWING": "그리기", "SELECTING": "색 선택",
                        "GRABBING": "잡기", "TRANSITION_OUT": "생성 준비",
                        "GENERATING": "생성 중", "SHOWING_RESULT": "완성",
                        "ERROR": "오류"}.get(state, "대기")

    def restore_drawing():
        nonlocal error_started, fist_started
        overlay.loading_elapsed = None
        overlay.error_message = None
        overlay.transition_progress = None
        error_started = fist_started = None
        reset_hand()
        overlay.update()

    def generation_failed(message):
        nonlocal error_started
        print(message, file=sys.stderr, flush=True)
        overlay.loading_elapsed = None
        overlay.error_message = message.split("\n")[0]
        transition("ERROR")
        error_started = time.monotonic()
        animation_timer.start()

    def close_result():
        nonlocal panel
        panel = None
        restore_drawing()

    def generation_succeeded(path):
        nonlocal panel
        overlay.loading_elapsed = None
        transition("SHOWING_RESULT")
        panel = ResultPanel(path, sketch_path, overlay.geometry())
        panel.closed.connect(close_result)
        panel.save_failed.connect(lambda message: print(message, file=sys.stderr))
        panel.show()
        animation_timer.stop()

    def start_generation():
        nonlocal bridge, sketch_path, generation_started
        try:
            sketch_path, result, log = overlay.canvas.export(config.ROOT / "output")
            generation_started = time.monotonic()
            overlay.loading_elapsed = 0.0
            transition("GENERATING")
            bridge = CodexBridge(sketch_path, result, log)
            bridge.succeeded.connect(generation_succeeded)
            bridge.failed.connect(generation_failed)
            bridge.start()
        except Exception as exc:
            generation_failed(str(exc))

    def animate_transition():
        nonlocal transition_started
        if state == "ERROR":
            if time.monotonic() - error_started >= config.ERROR_SECONDS:
                animation_timer.stop()
                restore_drawing()
            overlay.update()
            return
        if state == "GENERATING":
            overlay.loading_elapsed = time.monotonic() - generation_started
            overlay.update()
            return
        if transition_started is None:
            return
        progress = min((time.monotonic() - transition_started) / config.TRANSITION_SECONDS, 1.0)
        overlay.transition_progress = progress
        overlay.update()
        if progress >= 1:
            transition_started = None
            start_generation()

    animation_timer = QTimer()
    animation_timer.setInterval(16)
    animation_timer.timeout.connect(animate_transition)

    def reset_selection():
        dwell.reset()
        overlay.hover_target = None
        overlay.hover_progress = 0.0

    def reset_hand():
        nonlocal last_erase_pos, last_draw_seen, ui_release_rect
        transition("IDLE")
        overlay.canvas.finish()
        gestures.reset()
        cursor_ema.reset()
        pinch_ema.reset()
        reset_selection()
        last_erase_pos = None
        last_draw_seen = None
        ui_release_rect = None
        overlay.palette_open = False
        throw.reset()

    def delete_thrown():
        if overlay.canvas.delete_grabbed():
            print("throw: grabbed stroke deleted", flush=True)
        throw.reset()

    def trigger_generation():
        nonlocal transition_started
        if state in ("TRANSITION_OUT", "GENERATING", "SHOWING_RESULT", "ERROR"):
            return
        if not overlay.canvas.strokes or (bridge is not None and bridge.isRunning()):
            return
        reset_hand()
        transition("TRANSITION_OUT")
        overlay.pen_down = False
        overlay.cursor_pos = None
        transition_started = time.monotonic()
        overlay.transition_progress = 0.0
        animation_timer.start()
        overlay.update()

    def edit_canvas(undo=False):
        if state in ("TRANSITION_OUT", "GENERATING", "SHOWING_RESULT", "ERROR"):
            return
        reset_hand()
        overlay.canvas.undo() if undo else overlay.canvas.clear()
        overlay.pen_down = False
        overlay.update()

    def toggle_debug():
        overlay.debug_visible = not overlay.debug_visible
        preview.debug_visible = overlay.debug_visible
        overlay.update()
        preview.update()

    def toggle_help():
        overlay.help_visible = not overlay.help_visible
        overlay.update()

    def toggle_camera():
        overlay.camera_background = not overlay.camera_background
        # 모드 사이의 좌표 점프가 기존 획/잡힌 획에 적용되지 않게 확정.
        if state not in ("TRANSITION_OUT", "GENERATING", "SHOWING_RESULT", "ERROR"):
            reset_hand()
            overlay.pen_down = False
            overlay.cursor_pos = None
        else:
            cursor_ema.reset()
            pinch_ema.reset()
        controls.bar.set_camera_mode(overlay.camera_background)
        overlay.update()

    def toggle_preview():
        if preview.isVisible():
            if controls.can_hide_preview():
                preview.hide()
            else:
                print("메뉴 막대를 사용할 수 없어 프리뷰를 유지합니다", flush=True)
        else:
            preview.show()
            preview.activateWindow()
            preview.setFocus()

    controls = Controls(preview, {
        "C": lambda: edit_canvas(), "Z": lambda: edit_canvas(True),
        "G": trigger_generation, "D": toggle_debug, "P": toggle_preview,
        "H": toggle_help, "V": toggle_camera, "Q": app.quit,
    })

    def update_debug(hands):
        lines = [f"상태: {state} · 후보: {gestures.candidate} · 확정: {gestures.current}"]
        for hand in hands:
            points = np.asarray(hand["lm"])[:, :2] * (config.CAMERA_WIDTH / config.CAMERA_HEIGHT, 1)
            ratios = [np.linalg.norm(points[tip] - points[0]) /
                      max(np.linalg.norm(points[joint] - points[0]), 1e-8)
                      for tip, joint in ((4,3),(8,6),(12,10),(16,14),(20,18))]
            fingers = " ".join(f"{name}:{ratio:.2f}{'↑' if ratio > config.FINGER_EXTEND_RATIO else '↓'}"
                               for name, ratio in zip(("엄지","검지","중지","약지","소지"), ratios))
            lines.extend([f"{hand['side']} · {classify(hand['lm'])} · 핀치: {pinch_ratio(hand['lm']):.2f}", fingers])
        if len(hands) == 2:
            delta = hands[0]["lm"][0,:2] - hands[1]["lm"][0,:2]
            distance = np.linalg.norm(delta * (1, config.CAMERA_HEIGHT / config.CAMERA_WIDTH))
            lines.append(f"양손 거리/폭: {distance:.3f} · 펼침: {spread.open_frames} · 확대 확인: {spread.confirm_frames}")
        if not hands:
            lines.append("손 없음")
        overlay.debug_text = "\n".join(lines)

    def on_frame(hands, image, fps):
        nonlocal active_side, transition_started, fist_started, last_erase_pos
        nonlocal last_draw_seen, last_hand_seen, ui_release_rect
        now = time.monotonic()
        preview.set_frame(image, hands)
        overlay.camera_image = image
        overlay.fps = fps
        if overlay.debug_visible:
            update_debug(hands)
        triggered = spread.update(hands, time.monotonic())
        overlay.spread_hint = None
        if len(hands) == 2 and state not in ("TRANSITION_OUT","GENERATING","SHOWING_RESULT","ERROR"):
            if not overlay.canvas.strokes:
                overlay.spread_hint = "먼저 그림을 그려주세요"
            elif all(spread.palm_open(h["lm"]) for h in hands):
                overlay.spread_hint = f"양손 인식됨 · 바깥으로 벌려주세요  {spread.progress:.0%}"
            else:
                overlay.spread_hint = "양손 인식됨 · 두 손의 손가락을 펼쳐주세요"
        if state == "SHOWING_RESULT":
            fist = bool(hands) and any(classify(h["lm"]) == "FIST" for h in hands)
            if fist:
                if fist_started is None:
                    fist_started = time.monotonic()
                elif time.monotonic() - fist_started >= config.RESULT_FIST_SECONDS:
                    overlay.canvas.clear()
                    if panel is not None:
                        panel.close()
            else:
                fist_started = None
            overlay.update()
            return
        if state in ("TRANSITION_OUT", "GENERATING", "ERROR"):
            overlay.update()
            return
        if triggered and overlay.canvas.strokes:
            trigger_generation()
            return
        if hands:
            last_hand_seen = now
            hand = next((h for h in hands if h["side"] == active_side), hands[0])
            if hand["side"] != active_side:
                # 한 손의 handedness 라벨이 흔들려도 획을 끊지 않는다.
                if active_side is None or len(hands) > 1:
                    reset_hand()
                active_side = hand["side"]
            x, y, _ = hand["lm"][INDEX_TIP]
            # 영상 속 손끝과 일치시킬 때는 EMA 지연도 제거한다.
            cursor_ema.alpha = 1.0 if overlay.camera_background else config.CURSOR_EMA_ALPHA
            pinch_ema.alpha = cursor_ema.alpha
            overlay.cursor_pos = cursor_ema(to_screen(x, y, overlay.width(), overlay.height(),
                                                    camera_aligned=overlay.camera_background))
            target = overlay.target_at(overlay.cursor_pos)
            if ui_release_rect is not None:
                from PySide6.QtCore import QPointF
                if not ui_release_rect.contains(QPointF(*overlay.cursor_pos)):
                    ui_release_rect = None
            if target == ("color_open", 0):
                overlay.palette_open = True
            if state != "GRABBING" and (overlay.palette_open or target is not None or ui_release_rect is not None):
                transition("SELECTING")
                overlay.canvas.finish()
                gestures.reset()
                overlay.pen_down = False
                last_draw_seen = last_erase_pos = None
                duration = (config.CLEAR_DWELL_SECONDS if target and target[0] == "clear"
                            else config.COLOR_DWELL_SECONDS)
                hover = target if target and target[0] != "color_open" else None
                action = dwell.update(hover, now, duration)
                overlay.hover_target, overlay.hover_progress = dwell.target, dwell.progress
                if action is not None:
                    kind, index = action
                    if kind in ("color", "eraser", "palette_close"):
                        if kind == "color":
                            overlay.eraser_selected = False
                            overlay.color = QColor(config.PALETTE_COLORS[index])
                        elif kind == "eraser":
                            overlay.eraser_selected = True
                        rect = (overlay.palette_close_rect() if kind == "palette_close" else
                                overlay.palette_rects()[index if kind == "color" else -1])
                        ui_release_rect = rect.adjusted(-12,-12,12,12)
                        overlay.palette_open = False
                        reset_selection()
                    elif kind == "clear":
                        overlay.canvas.clear()
                overlay.update()
                return
            reset_selection()
            raw = classify(hand["lm"], pinching=gestures.candidate == "PINCH",
                           drawing=state == "DRAWING")
            stable = gestures.update(raw)
            # 펜 업 후보 프레임은 즉시 점 추가를 멈춘다.
            # 상태 전환만 디바운스하여 주먹으로 접는 궤적이 그려지지 않게 한다.
            drawing = raw == "DRAW" and (stable == "DRAW" or state == "DRAWING")
            if drawing:
                last_draw_seen = now
            preserve_stroke = (state == "DRAWING" and not drawing and
                               last_draw_seen is not None and now-last_draw_seen < config.STROKE_GAP_SECONDS
                               and not (raw == stable and stable in ("FIST","PINCH","SELECT")))
            selecting = raw == "SELECT" and stable == "SELECT"
            grabbing = raw == "PINCH" and stable == "PINCH"
            if raw == "PINCH":
                px, py = (hand["lm"][4, :2] + hand["lm"][8, :2]) / 2
                raw_pinch_pos = to_screen(px, py, overlay.width(), overlay.height(),
                                          camera_aligned=overlay.camera_background, clamp=False)
                pinch_pos = pinch_ema(raw_pinch_pos)
                overlay.cursor_pos = np.clip(pinch_pos, (0,0), (overlay.width()-1,overlay.height()-1))
            else:
                pinch_ema.reset()
            starting_grab = grabbing and state != "GRABBING"
            if state == "GRABBING" and not grabbing and raw != "PINCH" and throw.ready(now):
                delete_thrown()
            transition("GRABBING" if grabbing else "DRAWING" if drawing or preserve_stroke
                       else "SELECTING" if selecting else "IDLE")
            if starting_grab:
                overlay.canvas.grab(pinch_pos)
                throw.reset()
            elif grabbing:
                overlay.canvas.move_grab(pinch_pos)
            if grabbing and overlay.canvas.grabbed is not None:
                throw.update(raw_pinch_pos, now, overlay.width(), overlay.height())
                if throw.ready(now, require_outside=True):
                    delete_thrown()
            if drawing:
                if overlay.eraser_selected:
                    point = overlay.cursor_pos
                    previous = point if last_erase_pos is None else last_erase_pos
                    distance = float(np.linalg.norm(point - previous))
                    steps = max(1, int(distance / (config.ERASER_RADIUS / 2)) + 1)
                    for step in range(1,steps+1):
                        overlay.canvas.erase_at(previous + (point - previous) * step / steps)
                    last_erase_pos = point.copy()
                elif overlay.canvas.active is None:
                    overlay.canvas.begin(overlay.cursor_pos, overlay.color.name())
                else:
                    overlay.canvas.add(overlay.cursor_pos)
            else:
                if not preserve_stroke:
                    overlay.canvas.finish()
                last_erase_pos = None
            overlay.pen_down = drawing
        else:
            if state == "GRABBING" and overlay.canvas.grabbed is not None and throw.ready(now):
                delete_thrown()
            reset_selection()
            if last_hand_seen is None or now-last_hand_seen >= config.STROKE_GAP_SECONDS:
                reset_hand()
                active_side = None
            overlay.cursor_pos = None
            overlay.pen_down = False
        overlay.fps = fps
        overlay.update()

    def on_failed(msg):
        print(msg, file=sys.stderr)
        app.quit()

    worker.frame_ready.connect(on_frame)
    worker.failed.connect(on_failed)
    def shutdown():
        controls.tray.hide()
        controls.bar.hide()
        animation_timer.stop()
        if bridge is not None and bridge.isRunning():
            bridge.requestInterruption()
            bridge.wait(4000)
        worker.requestInterruption()
        worker.wait(2000)

    app.aboutToQuit.connect(shutdown)

    overlay.show()
    preview.show()
    controls.show_bar(overlay.camera_background)
    worker.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
