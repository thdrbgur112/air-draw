"""프리뷰 포커스 단축키와 메뉴 막대. 전역 키 감시 권한을 사용하지 않음."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QKeySequence, QShortcut
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget, QHBoxLayout, QPushButton
from PySide6.QtGui import QGuiApplication
from overlay import pin_window


class ControlBar(QWidget):
    """오버레이와 별개의 클릭 가능한 조작 창. 카메라/프리뷰 상태와 무관하게 유지."""
    def __init__(self, callbacks):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setObjectName("airDrawControlBar")
        self.setStyleSheet(
            "#airDrawControlBar { background: #ffffff; border: 1px solid #aaaaaa; border-radius: 10px; }"
            "QPushButton { background: #eeeeee; color: #222222; border: none; border-radius: 7px; padding: 10px 14px; }"
            "QPushButton:hover { background: #dcecff; }"
            "QPushButton#quitButton { background: #c62828; color: white; }"
        )
        layout = QHBoxLayout(self)
        self.camera_button = QPushButton()
        self.camera_button.clicked.connect(callbacks["V"])
        layout.addWidget(self.camera_button)
        self.buttons = {"V": self.camera_button}
        for key, label in (("G", "AI 그림 만들기"), ("P", "작은 카메라"),
                           ("H", "사용법"), ("Q", "앱 종료")):
            button = QPushButton(label)
            if key == "Q": button.setObjectName("quitButton")
            button.clicked.connect(callbacks[key])
            layout.addWidget(button)
            self.buttons[key] = button
        self.set_camera_mode(True)

    def set_camera_mode(self, enabled):
        self.camera_button.setText("전체화면 끄기" if enabled else "전체화면 카메라 켜기")
        self.camera_button.setToolTip("투명 오버레이로 전환" if enabled else "카메라 영상을 화면 전체에 표시")
        self.adjustSize()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.bottom() - self.height() - 16)

    def showEvent(self, event):
        super().showEvent(event)
        window = pin_window(self, level_offset=3)
        if window is not None:
            window.setIgnoresMouseEvents_(False)


class Controls:
    def __init__(self, preview, callbacks):
        self.menu = QMenu()
        self.shortcuts = []
        self.actions = {}
        for key, label in (("C", "지우기"), ("Z", "마지막 획 취소"), ("G", "AI 생성"),
                           ("D", "디버그 표시"), ("P", "프리뷰 표시 / 숨기기"),
                           ("H", "사용법 표시"), ("V", "전체화면 카메라"), ("Q", "종료")):
            action = self.menu.addAction(f"{label}  (Ctrl+Option+{key})")
            action.triggered.connect(callbacks[key])
            self.actions[key] = action
            shortcut = QShortcut(QKeySequence(f"Ctrl+Alt+{key}"), preview)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.setAutoRepeat(False)
            shortcut.activated.connect(callbacks[key])
            self.shortcuts.append(shortcut)
        pixmap = QPixmap(22, 22)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(30, 120, 220), 3, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(4, 18, 17, 5)
        painter.drawLine(4, 18, 10, 18)
        painter.end()
        self.tray = QSystemTrayIcon(QIcon(pixmap), preview)
        self.tray.setToolTip("Air Draw")
        self.tray.setContextMenu(self.menu)
        self.tray.show()
        self.bar = ControlBar(callbacks)

    def show_bar(self, camera_enabled):
        self.bar.set_camera_mode(camera_enabled)
        self.bar.show()

    def can_hide_preview(self):
        return QSystemTrayIcon.isSystemTrayAvailable()
