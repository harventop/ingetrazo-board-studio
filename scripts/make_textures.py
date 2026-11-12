"""Генерує безшовні текстури для Board Studio у board_studio/textures/.

Запуск (Python IngeTrazo, де є numpy і PySide6):
    flatpak run --command=python3 com.ingetrazo.IngeTrazo -I scripts/make_textures.py

Шум будується через FFT, тому він періодичний — текстури тайляться без швів.
Ось U зображення (ширина) — вздовж волокон / довжини панелі.
"""
from pathlib import Path

import numpy as np
from PySide6.QtGui import QImage

OUT = Path(__file__).resolve().parents[1] / "board_studio" / "textures"
rng = np.random.default_rng(7)


def noise(h, w, fu, fv, power=2.0):
    """Періодичний шум [0..1]; fu/fv — масштаб частот уздовж U (ширина) / V (висота)."""
    spec = np.fft.fft2(rng.standard_normal((h, w)))
    ky = np.fft.fftfreq(h)[:, None] * h / fv
    kx = np.fft.fftfreq(w)[None, :] * w / fu
    k = np.sqrt(kx ** 2 + ky ** 2)
    k[0, 0] = 1.0
    n = np.real(np.fft.ifft2(spec / k ** power))
    return (n - n.min()) / (n.max() - n.min())


def ramp(t, colors):
    """Колірна шкала: t [0..1] → RGB за опорними кольорами."""
    stops = np.linspace(0, 1, len(colors))
    c = np.array(colors, float)
    return np.stack([np.interp(t, stops, c[:, i]) for i in range(3)], -1)


def save(rgb, name):
    OUT.mkdir(parents=True, exist_ok=True)
    a = np.ascontiguousarray(np.clip(rgb, 0, 255).astype(np.uint8))
    h, w, _ = a.shape
    QImage(a.data, w, h, 3 * w, QImage.Format_RGB888).copy().save(str(OUT / name))
    print("wrote", OUT / name)


def oak(h=512, w=1024):
    y = np.arange(h)[:, None] / h
    warp = noise(h, w, 2, 6) * 2.2                         # плавні вигини волокон
    rings = 0.5 + 0.5 * np.sin(2 * np.pi * (9 * y + warp))  # річні кільця (9 періодів на висоту)
    streak = noise(h, w, 1.5, 90, 1.2)                      # дрібні пори вздовж волокон
    t = 0.55 * rings ** 1.6 + 0.45 * streak
    rgb = ramp(t, [(222, 186, 138), (198, 154, 104), (166, 120, 76), (130, 88, 52)])
    pores = noise(h, w, 40, 300, 0.6) > 0.82                # темні штрихи-пори
    rgb[pores] *= 0.82
    save(rgb, "oak.png")


def chipboard(n=512, count=9000):
    """Тріски: тисячі дрібних витягнутих плям різних відтінків поверх тла.
    Кожна малюється ще й зі зсувом ±n — тож текстура безшовна."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QPainter

    base = ramp(noise(n, n, 30, 30, 1.0), [(150, 112, 68), (190, 150, 100)])
    a = np.ascontiguousarray(base.astype(np.uint8))
    img = QImage(a.data, n, n, 3 * n, QImage.Format_RGB888).copy()
    palette = np.array([(214, 180, 128), (196, 156, 104), (172, 130, 80),
                        (232, 204, 156), (128, 92, 54), (98, 70, 42)], float)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    for _ in range(count):
        c = palette[rng.integers(len(palette))] * rng.uniform(0.9, 1.08)
        p.setBrush(QColor(*np.clip(c, 0, 255).astype(int)))
        x, y = rng.uniform(0, n, 2)
        length, width = rng.uniform(3, 14), rng.uniform(1.2, 3.5)
        angle = rng.normal(0, 25)                            # тріски лягають переважно вздовж
        for dx in (-n, 0, n):
            for dy in (-n, 0, n):
                p.save()
                p.translate(x + dx, y + dy)
                p.rotate(angle)
                p.drawEllipse(QPointF(0, 0), length / 2, width / 2)
                p.restore()
    p.end()
    OUT.mkdir(parents=True, exist_ok=True)
    img.save(str(OUT / "chipboard.png"))
    print("wrote", OUT / "chipboard.png")


def fibreboard(n=256):
    t = 0.7 * noise(n, n, 60, 60, 1.0) + 0.3 * noise(n, n, 6, 6, 2.0)
    save(ramp(t, [(132, 96, 60), (160, 120, 78), (182, 142, 96)]), "fibreboard.png")


if __name__ == "__main__":
    oak()
    chipboard()
    fibreboard()
