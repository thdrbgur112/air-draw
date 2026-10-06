"""독립적인 획 데이터와 한 번의 Chaikin 스무딩."""
from dataclasses import dataclass, field
from math import hypot
from dataclasses import asdict
from datetime import datetime
import json

import config


@dataclass
class Stroke:
    id: int
    color: str
    thickness: float
    points: list = field(default_factory=list)

    @property
    def bbox(self):
        xs, ys = zip(*self.points)
        return min(xs), min(ys), max(xs), max(ys)


class Canvas:
    def __init__(self):
        self.strokes = []
        self.active = None
        self.next_id = 1
        self.grabbed = None
        self.grab_origin = None
        self.grab_points = None

    def clear(self):
        self.release()
        self.active = None
        self.strokes.clear()

    def undo(self):
        self.finish()
        self.release()
        if self.strokes:
            self.strokes.pop()

    def erase_at(self, point, radius=config.ERASER_RADIUS):
        """원 안의 선분을 잘라 획을 나눈다. 색과 두께는 유지."""
        self.finish()
        self.release()
        cx, cy = point
        result = []
        for stroke in self.strokes:
            r = radius + stroke.thickness / 2
            if len(stroke.points) == 1:
                x,y = stroke.points[0]
                if hypot(x-cx,y-cy) > r:
                    result.append(stroke)
                continue
            pieces, current = [], []
            for a,b in zip(stroke.points,stroke.points[1:]):
                dx,dy = b[0]-a[0],b[1]-a[1]
                ox,oy = a[0]-cx,a[1]-cy
                aa = dx*dx+dy*dy
                bb = 2*(ox*dx+oy*dy)
                cc = ox*ox+oy*oy-r*r
                disc = bb*bb-4*aa*cc
                cuts = [0.,1.]
                if aa > 1e-12 and disc > 0:
                    root = disc**.5
                    cuts.extend(t for t in ((-bb-root)/(2*aa),(-bb+root)/(2*aa)) if 0 < t < 1)
                cuts.sort()
                for lo,hi in zip(cuts,cuts[1:]):
                    mid=(lo+hi)/2
                    outside=hypot(ox+mid*dx,oy+mid*dy)>r
                    if outside:
                        start=(a[0]+lo*dx,a[1]+lo*dy)
                        end=(a[0]+hi*dx,a[1]+hi*dy)
                        if not current:
                            current=[start]
                        elif hypot(current[-1][0]-start[0],current[-1][1]-start[1])>1e-6:
                            pieces.append(current); current=[start]
                        if end != current[-1]: current.append(end)
                    elif current:
                        pieces.append(current); current=[]
            if current: pieces.append(current)
            for i,points in enumerate(pieces):
                identifier = stroke.id if i == 0 else self.next_id
                if i: self.next_id += 1
                result.append(Stroke(identifier,stroke.color,stroke.thickness,points))
        self.strokes = result

    def export(self, directory):
        from pathlib import Path
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
        self.finish()
        if not self.strokes:
            raise ValueError("그림이 없습니다")
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        png = directory / f"sketch_{stamp}.png"
        data = directory / f"sketch_{stamp}.json"
        boxes = [s.bbox for s in self.strokes]
        padding = max(s.thickness for s in self.strokes) / 2
        left = min(b[0] for b in boxes) - padding
        top = min(b[1] for b in boxes) - padding
        right = max(b[2] for b in boxes) + padding
        bottom = max(b[3] for b in boxes) + padding
        size = config.SKETCH_SIZE
        scale = (size - 2 * config.SKETCH_MARGIN) / max(right - left, bottom - top, 1)
        image = QImage(size, size, QImage.Format_ARGB32)
        image.fill(Qt.white)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(size / 2, size / 2)
        painter.scale(scale, scale)
        painter.translate(-(left + right) / 2, -(top + bottom) / 2)
        for stroke in self.strokes:
            painter.setPen(QPen(QColor(stroke.color), stroke.thickness,
                                Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            if len(stroke.points) == 1:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(stroke.color))
                radius = stroke.thickness / 2
                painter.drawEllipse(QPointF(*stroke.points[0]), radius, radius)
                painter.setBrush(Qt.NoBrush)
            else:
                path = QPainterPath(QPointF(*stroke.points[0]))
                for point in stroke.points[1:]:
                    path.lineTo(QPointF(*point))
                painter.drawPath(path)
        painter.end()
        if not image.save(str(png), "PNG"):
            raise OSError("스케치 PNG 저장 실패")
        data.write_text(json.dumps([asdict(s) | {"bbox": s.bbox} for s in self.strokes],
                                   ensure_ascii=False, indent=2), encoding="utf-8")
        return png, directory / f"result_{stamp}.png", directory / f"codex_{stamp}.log"

    def hit_test(self, point, threshold=config.GRAB_HIT_DISTANCE):
        best, best_distance = None, float("inf")
        x, y = point
        for stroke in reversed(self.strokes):
            left, top, right, bottom = stroke.bbox
            limit = threshold + stroke.thickness / 2
            if not (left - limit <= x <= right + limit and top - limit <= y <= bottom + limit):
                continue
            points = stroke.points
            segments = zip(points, points[1:]) if len(points) > 1 else [(points[0], points[0])]
            for a, b in segments:
                dx, dy = b[0] - a[0], b[1] - a[1]
                length_squared = dx * dx + dy * dy
                t = (max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / length_squared))
                     if length_squared else 0.0)
                distance = hypot(x - (a[0] + t * dx), y - (a[1] + t * dy))
                if distance <= limit and distance < best_distance:
                    best, best_distance = stroke, distance
        return best

    def grab(self, point):
        self.finish()
        self.release()
        self.grabbed = self.hit_test(point)
        if self.grabbed is not None:
            self.grab_origin = tuple(map(float, point))
            self.grab_points = self.grabbed.points.copy()

    def move_grab(self, point):
        if self.grabbed is None:
            return
        dx, dy = point[0] - self.grab_origin[0], point[1] - self.grab_origin[1]
        self.grabbed.points = [(x + dx, y + dy) for x, y in self.grab_points]

    def release(self):
        self.grabbed = None
        self.grab_origin = None
        self.grab_points = None

    def delete_grabbed(self):
        if self.grabbed is None:
            return False
        identifier = self.grabbed.id
        self.strokes = [stroke for stroke in self.strokes if stroke.id != identifier]
        self.release()
        return True

    def begin(self, point, color, thickness=config.STROKE_THICKNESS):
        self.finish()
        self.active = Stroke(self.next_id, color, thickness, [tuple(map(float, point))])
        self.next_id += 1
        self.strokes.append(self.active)

    def add(self, point):
        if self.active is None:
            return
        point = tuple(map(float, point))
        last = self.active.points[-1]
        if hypot(point[0] - last[0], point[1] - last[1]) >= config.STROKE_MIN_DISTANCE:
            self.active.points.append(point)

    def finish(self):
        if self.active is not None and len(self.active.points) > 2:
            points = self.active.points
            smooth = [points[0]]
            for a, b in zip(points, points[1:]):
                smooth.extend([
                    (0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]),
                    (0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]),
                ])
            smooth.append(points[-1])
            self.active.points = smooth
        self.active = None
