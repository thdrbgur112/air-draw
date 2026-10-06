from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget
from mediapipe.tasks.python.vision import HandLandmarksConnections

import config
from overlay import pin_window

CONNECTIONS = [(c.start, c.end) for c in HandLandmarksConnections.HAND_CONNECTIONS]


class Preview(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        w, h = config.PREVIEW_SIZE
        self.setFixedSize(w, h)
        g = QGuiApplication.primaryScreen().availableGeometry()
        m = config.PREVIEW_MARGIN
        self.move(g.right() - w - m, g.bottom() - h - m)
        self.image = None
        self.hands = []
        self.debug_visible = False
        self.setFocusPolicy(Qt.StrongFocus)
        self.setToolTip("클릭 후 Ctrl+Option+C/Z/G/D/P/H/Q · 메뉴 막대 Air Draw")

    def mousePressEvent(self, event):
        self.activateWindow()
        self.setFocus(Qt.MouseFocusReason)
        super().mousePressEvent(event)

    def showEvent(self, e):
        super().showEvent(e)
        pin_window(self, level_offset=1)

    def set_frame(self, image, hands):
        self.image, self.hands = image, hands
        self.update()

    def paintEvent(self, _):
        if self.image is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.drawImage(self.rect(), self.image)
        w, h = self.width(), self.height()
        for hand in self.hands:
            pts = [QPointF(x * w, y * h) for x, y, _ in hand["lm"]]
            p.setPen(QPen(QColor(0, 255, 120), 1.5))
            for a, b in CONNECTIONS:
                p.drawLine(pts[a], pts[b])
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 60, 60))
            for pt in pts:
                p.drawEllipse(pt, 2, 2)
            if self.debug_visible:
                p.setFont(QFont("Menlo", 8))
                p.setPen(QColor(255, 255, 255))
                for number, pt in enumerate(pts):
                    p.drawText(pt + QPointF(3, -3), str(number))
