"""결과 영역만 마우스 입력을 받는 별도 패널."""
import shutil
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QPropertyAnimation
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtWidgets import (QWidget, QLabel, QPushButton, QVBoxLayout,
                              QHBoxLayout, QGraphicsDropShadowEffect)
import config
from overlay import pin_window


class ResultPanel(QWidget):
    closed = Signal()
    save_failed = Signal(str)

    def __init__(self, result, sketch, screen):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.result = Path(result)
        self.setStyleSheet("QWidget { background: white; color: #333; border-radius: 12px; }"
                           "QPushButton { padding: 8px 16px; background: #eeeeee; }")
        layout = QVBoxLayout(self)
        image = QLabel()
        pixmap = QPixmap(str(result))
        side = max(100, min(640, screen.width() - 100, screen.height() - 160))
        image.setPixmap(pixmap.scaled(side, side, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        image.setAlignment(Qt.AlignCenter)
        shadow = QGraphicsDropShadowEffect(image)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 90))
        image.setGraphicsEffect(shadow)
        layout.addWidget(image)
        row = QHBoxLayout()
        close = QPushButton("닫기")
        close.clicked.connect(self.close)
        self.save_button = QPushButton("저장")
        self.save_button.clicked.connect(self.save)
        row.addWidget(close)
        row.addWidget(self.save_button)
        row.addStretch()
        thumbnail = QLabel()
        thumbnail.setPixmap(QPixmap(str(sketch)).scaled(80, 80, Qt.KeepAspectRatio,
                                                        Qt.SmoothTransformation))
        row.addWidget(thumbnail)
        layout.addLayout(row)
        self.adjustSize()
        self.move(screen.center() - self.rect().center())
        self.animation = QPropertyAnimation(self, b"windowOpacity", self)
        self.animation.setDuration(300)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)

    def showEvent(self, event):
        super().showEvent(event)
        pin_window(self, 2)
        self.animation.start()

    def save(self):
        try:
            directory = config.ROOT / "gallery"
            directory.mkdir(exist_ok=True)
            destination = directory / self.result.name
            if not destination.exists():
                shutil.copy2(self.result, destination)
            self.save_button.setText("저장 완료")
            print(f"saved: {destination}", flush=True)
        except OSError as exc:
            self.save_button.setText("저장 실패 · 재시도")
            self.save_failed.emit(str(exc))

    def closeEvent(self, event):
        super().closeEvent(event)
        self.closed.emit()
