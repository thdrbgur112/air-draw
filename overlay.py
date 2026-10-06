from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

import config
from canvas import Canvas


def pin_window(widget, level_offset=0):
    """모든 Space·전체화면 앱 위에 표시. pyobjc 없으면 Qt 플래그만으로 동작."""
    try:
        import AppKit
        import objc
    except ImportError:
        return
    win = objc.objc_object(c_void_p=int(widget.winId())).window()
    win.setCollectionBehavior_(
        AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
        | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
        | AppKit.NSWindowCollectionBehaviorStationary
    )
    win.setLevel_(AppKit.NSStatusWindowLevel + level_offset)
    win.setHidesOnDeactivate_(False)
    return win


def hide_from_dock():
    """Dock 아이콘 없는 액세서리 앱으로 전환 (전체화면 앱 Space 위에도 뜨게 함)."""
    try:
        import AppKit
    except ImportError:
        return
    AppKit.NSApplication.sharedApplication().setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)


class Overlay(QWidget):
    def __init__(self):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowTransparentForInput
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setGeometry(QGuiApplication.primaryScreen().geometry())
        self.cursor_pos = None
        self.pen_down = False
        self.color = QColor(config.DEFAULT_COLOR)
        self.mode = "대기"
        self.fps = 0.0
        self.canvas = Canvas()
        self.hover_target = None
        self.hover_progress = 0.0
        self.transition_progress = None
        self.loading_elapsed = None
        self.error_message = None
        self.debug_visible = False
        self.help_visible = False
        self.debug_text = "손 없음"
        self.eraser_selected = False
        self.camera_background = config.CAMERA_BACKGROUND_DEFAULT
        self.camera_image = None
        self.palette_open = False
        self.spread_hint = None

    def showEvent(self, e):
        super().showEvent(e)
        win = pin_window(self)
        if win is not None:
            win.setIgnoresMouseEvents_(True)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.camera_background and self.camera_image is not None:
            p.drawImage(self.rect(), self.camera_image)
        self._draw_strokes(p)
        self._draw_hud(p)
        self._draw_controls(p)
        self._draw_status(p)
        self._draw_guides(p)
        if self.spread_hint:
            rect = QRectF(self.width()/2-250,self.height()-145,500,36)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255,255,255,225))
            p.drawRoundedRect(rect,10,10)
            p.setPen(QColor(45,45,45))
            p.setFont(QFont("Apple SD Gothic Neo",13))
            p.drawText(rect,Qt.AlignCenter,self.spread_hint)
        if self.cursor_pos is not None:
            self._draw_cursor(p)

    def _draw_guides(self, p):
        top = 90
        for visible, text in ((self.debug_visible, self.debug_text),
                              (self.help_visible, config.HELP_TEXT)):
            if not visible:
                continue
            p.setFont(QFont("Apple SD Gothic Neo", 12))
            lines = text.splitlines()
            width = max(p.fontMetrics().horizontalAdvance(line) for line in lines) + 24
            height = len(lines) * 21 + 20
            rect = QRectF(16, top, width, height)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 210))
            p.drawRoundedRect(rect, 10, 10)
            p.setPen(QColor(45, 45, 45))
            p.drawText(rect.adjusted(12, 10, -12, -10), Qt.AlignLeft | Qt.AlignTop, text)
            top += height + 12

    def _draw_status(self, p):
        if self.loading_elapsed is None and not self.error_message:
            return
        rect = QRectF(self.width() / 2 - 220, self.height() / 2 - 45, 440, 90)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 220))
        p.drawRoundedRect(rect, 12, 12)
        p.setPen(QColor(60, 60, 60))
        p.setFont(QFont("Apple SD Gothic Neo", 13))
        if self.error_message:
            p.drawText(rect.adjusted(12, 8, -12, -8), Qt.AlignCenter | Qt.TextWordWrap,
                       self.error_message)
        else:
            p.drawText(rect, Qt.AlignCenter, f"생성 중  {self.loading_elapsed:.0f}초")
            p.setPen(QPen(QColor(30, 120, 220), 3, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(QRectF(rect.left() + 18, rect.center().y() - 12, 24, 24),
                      int(-self.loading_elapsed * 240 * 16), 250 * 16)

    def palette_rects(self):
        diameter = 2 * config.PALETTE_RADIUS
        count = len(config.PALETTE_COLORS) + 1
        width = 3 * diameter + 2 * config.PALETTE_GAP
        left, top = (self.width() - width) / 2, (self.height() - width) / 2
        return [QRectF(left + (i % 3) * (diameter + config.PALETTE_GAP),
                       top + (i // 3) * (diameter + config.PALETTE_GAP), diameter, diameter)
                for i in range(count)]

    def color_button_rect(self):
        width, height = config.COLOR_BUTTON_SIZE
        return QRectF(self.width() - config.CONTROL_MARGIN - width,
                      config.PALETTE_TOP, width, height)

    def palette_close_rect(self):
        rects = self.palette_rects()
        return QRectF(rects[-1].right() - 32, rects[0].top() - 52, 40, 32)

    def clear_rect(self):
        width, height = config.CLEAR_BUTTON_SIZE
        return QRectF(config.CONTROL_MARGIN,
                      self.height() - config.CONTROL_MARGIN - height, width, height)

    def target_at(self, point):
        point = QPointF(*point)
        if self.color_button_rect().contains(point):
            return ("color_open", 0)
        if self.palette_open:
            if self.palette_close_rect().contains(point):
                return ("palette_close", 0)
            for i, rect in enumerate(self.palette_rects()):
                offset = point - rect.center()
                if offset.x() ** 2 + offset.y() ** 2 <= config.PALETTE_RADIUS ** 2:
                    return ("eraser", 0) if i == len(config.PALETTE_COLORS) else ("color", i)
        if self.clear_rect().contains(point):
            return ("clear", 0)
        return None

    def _draw_controls(self, p):
        button = self.color_button_rect()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255,255,255,230))
        p.drawRoundedRect(button, 10, 10)
        p.setPen(QColor(45,45,45))
        p.setFont(QFont("Apple SD Gothic Neo", 15))
        p.drawText(button, Qt.AlignCenter, "Color")
        clear = self.clear_rect()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255,255,255,210))
        p.drawRoundedRect(clear, 10, 10)
        p.setPen(QColor(60,60,60))
        p.drawText(clear, Qt.AlignCenter, "지우기")
        if not self.palette_open:
            self._draw_hover_ring(p)
            return
        rects = self.palette_rects()
        panel = rects[0].united(rects[-1]).adjusted(-22, -60, 22, 22)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 200))
        p.drawRoundedRect(panel, 12, 12)
        p.setPen(QColor(45,45,45))
        p.setFont(QFont("Apple SD Gothic Neo", 14))
        p.drawText(QRectF(panel.left()+16,panel.top()+12,panel.width()-65,32),
                   Qt.AlignLeft | Qt.AlignVCenter, "색 선택 · 0.5초 머무르기")
        p.drawText(self.palette_close_rect(), Qt.AlignCenter, "닫기")
        for i, rect in enumerate(rects[:-1]):
            color = QColor(config.PALETTE_COLORS[i])
            p.setPen(QPen(QColor(110, 110, 110), 1))
            p.setBrush(color)
            p.drawEllipse(rect)
            if color == self.color and not self.eraser_selected:
                p.setPen(QPen(QColor(35, 35, 35), 2))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(rect.adjusted(-4, -4, 4, 4))
        eraser = rects[-1]
        p.setPen(QPen(QColor(35,35,35), 2 if self.eraser_selected else 1))
        p.setBrush(QColor(235,235,235))
        p.drawEllipse(eraser)
        p.setFont(QFont("Apple SD Gothic Neo", 10))
        p.drawText(eraser, Qt.AlignCenter, "지우개")
        if self.eraser_selected:
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(eraser.adjusted(-4,-4,4,4))
        self._draw_hover_ring(p)

    def _draw_hover_ring(self, p):
        rects = self.palette_rects()
        clear = self.clear_rect()
        if self.hover_target is not None and self.hover_progress > 0:
            kind, index = self.hover_target
            if kind in ("color", "eraser"):
                ring = rects[index if kind == "color" else -1].adjusted(-6, -6, 6, 6)
            elif kind == "palette_close":
                ring = self.palette_close_rect().adjusted(-3,-3,3,3)
            else:
                diameter = clear.height() + 8
                ring = QRectF(clear.right() + 8, clear.center().y() - diameter / 2,
                              diameter, diameter)
            p.setPen(QPen(QColor(30, 120, 220), 3, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            p.drawArc(ring, 90 * 16, -int(360 * 16 * self.hover_progress))

    def _draw_strokes(self, p):
        p.save()
        if self.transition_progress is not None:
            progress = self.transition_progress
            scale = 1 + (config.TRANSITION_MAX_SCALE - 1) * progress
            p.setOpacity(1 - progress)
            p.translate(self.width() / 2, self.height() / 2)
            p.scale(scale, scale)
            p.translate(-self.width() / 2, -self.height() / 2)
        for stroke in self.canvas.strokes:
            grabbed = stroke is self.canvas.grabbed
            thickness = stroke.thickness + (config.GRAB_THICKNESS_EXTRA if grabbed else 0)
            if grabbed:
                p.setPen(QPen(QColor(30, 120, 220, 90),
                              thickness + config.GRAB_HIGHLIGHT_EXTRA,
                              Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.setBrush(Qt.NoBrush)
                if len(stroke.points) == 1:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(30, 120, 220, 90))
                    radius = (thickness + config.GRAB_HIGHLIGHT_EXTRA) / 2
                    p.drawEllipse(QPointF(*stroke.points[0]), radius, radius)
                else:
                    highlight = QPainterPath(QPointF(*stroke.points[0]))
                    for point in stroke.points[1:]:
                        highlight.lineTo(QPointF(*point))
                    p.drawPath(highlight)
            p.setPen(QPen(QColor(stroke.color), thickness,
                          Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            if len(stroke.points) == 1:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(stroke.color))
                radius = thickness / 2
                p.drawEllipse(QPointF(*stroke.points[0]), radius, radius)
            else:
                path = QPainterPath(QPointF(*stroke.points[0]))
                for point in stroke.points[1:]:
                    path.lineTo(QPointF(*point))
                p.drawPath(path)
        p.restore()

    def _draw_cursor(self, p):
        c = QPointF(*self.cursor_pos)
        r = config.ERASER_RADIUS if self.eraser_selected else config.CURSOR_RADIUS
        p.setPen(QPen(QColor(255, 255, 255, 220), 5))  # 어두운/밝은 배경 모두에서 보이게 흰 테두리
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, r, r)
        p.setPen(QPen(QColor(110,110,110) if self.eraser_selected else self.color, 2.5))
        p.setBrush(self.color if self.pen_down and not self.eraser_selected else Qt.NoBrush)
        p.drawEllipse(c, r, r)

    def _draw_hud(self, p):
        text = f"{self.mode}   {self.fps:4.0f} FPS"
        p.setFont(QFont("Apple SD Gothic Neo", 13))
        w = p.fontMetrics().horizontalAdvance(text) + 20
        rect = QRectF(16, 40, w, 28)  # 메뉴바 아래
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 190))
        p.drawRoundedRect(rect, 8, 8)
        p.setPen(QColor(60, 60, 60))
        p.drawText(rect, Qt.AlignCenter, text)
