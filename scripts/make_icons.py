"""Іконки команд Board Studio (128×128) у board_studio/icons/.

Запуск (Python IngeTrazo):
    flatpak run --command=python3 --env=QT_QPA_PLATFORM=offscreen com.ingetrazo.IngeTrazo -I scripts/make_icons.py
"""
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QGuiApplication, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPolygonF)

OUT = Path(__file__).resolve().parents[1] / "board_studio" / "icons"
WOOD = (QColor(232, 196, 150), QColor(205, 160, 110))
EDGE = QColor(170, 120, 75)
INK = QColor(70, 45, 25)


def board(p):
    """Плита в ізометрії, як на new.png: фронт, верхній і правий торці."""
    front = QPolygonF([QPointF(22, 30), QPointF(92, 14), QPointF(92, 100), QPointF(22, 116)])
    side = QPolygonF([QPointF(92, 14), QPointF(104, 22), QPointF(104, 108), QPointF(92, 100)])
    bottom = QPolygonF([QPointF(22, 116), QPointF(92, 100), QPointF(104, 108), QPointF(34, 124)])
    g = QLinearGradient(22, 30, 92, 100)
    g.setColorAt(0, WOOD[0])
    g.setColorAt(1, WOOD[1])
    p.setPen(QPen(INK, 2.5))
    p.setBrush(QBrush(g))
    p.drawPolygon(front)
    p.setBrush(EDGE)
    p.drawPolygon(side)
    p.drawPolygon(bottom)
    p.setPen(QPen(QColor(190, 145, 95), 1.5))
    for k in range(5):                                  # волокна
        y = 42 + k * 15
        path = QPainterPath(QPointF(28, y + 4))
        path.cubicTo(QPointF(50, y - 6), QPointF(66, y + 6), QPointF(88, y - 12))
        p.drawPath(path)


def badge(p, draw):
    p.setPen(QPen(INK, 2.5))
    p.setBrush(QColor(255, 255, 255, 235))
    p.drawEllipse(QRectF(62, 62, 60, 60))
    draw(p)


def edgeband(p):
    # крайка: кольорові смуги на правому й нижньому торцях
    p.setPen(QPen(INK, 2.5))
    p.setBrush(QColor(60, 140, 220))
    p.drawPolygon(QPolygonF([QPointF(92, 14), QPointF(104, 22), QPointF(104, 108), QPointF(92, 100)]))
    p.setBrush(QColor(60, 179, 113))
    p.drawPolygon(QPolygonF([QPointF(22, 116), QPointF(92, 100), QPointF(104, 108), QPointF(34, 124)]))


def properties(p):
    # напрямок текстури
    def arrow(q):
        q.setPen(QPen(QColor(220, 60, 50), 6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        q.drawLine(QPointF(92, 112), QPointF(92, 74))
        q.drawPolyline(QPolygonF([QPointF(80, 86), QPointF(92, 72), QPointF(104, 86)]))
    badge(p, arrow)


def dowels(p):
    def pins(q):
        for x in (78, 96):
            q.setPen(QPen(INK, 2))
            q.setBrush(QColor(214, 170, 110))
            q.drawRoundedRect(QRectF(x - 6, 70, 12, 44), 5, 5)
            q.setPen(QPen(QColor(150, 105, 60), 1.5))
            for y in range(76, 110, 6):
                q.drawLine(QPointF(x - 5, y), QPointF(x + 5, y + 3))
    badge(p, pins)


def dxf(p):
    def label(q):
        q.setPen(QPen(QColor(30, 90, 170)))
        f = QFont("Sans", 15, QFont.Bold)
        q.setFont(f)
        q.drawText(QRectF(62, 62, 60, 60), Qt.AlignCenter, "DXF")
    badge(p, label)


def main():
    app = QGuiApplication.instance() or QGuiApplication([])
    for name, extra in (("properties", properties), ("dowels", dowels), ("dxf", dxf),
                        ("edgeband", edgeband)):
        img = QImage(128, 128, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        board(p)
        extra(p)
        p.end()
        img.save(str(OUT / f"{name}.png"))
        print("wrote", OUT / f"{name}.png")
    del app


if __name__ == "__main__":
    main()
